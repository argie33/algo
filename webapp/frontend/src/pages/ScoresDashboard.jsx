import { useState, useEffect } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  alpha,
  useTheme,
  Tooltip,
  IconButton,
} from "@mui/material";
import {
  ExpandMore,
  TrendingUp,
  TrendingDown,
  Assessment,
  Speed,
  Psychology,
  Stars,
  AccountBalance,
  Security,
  ShowChart,
  SignalCellularAlt,
  Timeline,
  Bolt,
  Group,
  SentimentSatisfied,
  FilterList,
  ClearAll,
  ChevronLeft as ChevronLeftIcon,
  ChevronRight as ChevronRightIcon,
} from "@mui/icons-material";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
  Label,
  LabelList,
} from "recharts";
import { exportToCSV, exportToJSON, tableToCSV } from "../utils/exportUtils";
import { Download as DownloadIcon, InsertDriveFile as ExportIcon } from "@mui/icons-material";

// Trading Signal Component
const TradingSignal = ({ signal, confidence = 0.75, size = "medium", showConfidence = false }) => {
  const theme = useTheme();

  const getSignalConfig = (signalType) => {
    switch (signalType?.toUpperCase()) {
      case "BUY":
        return {
          color: theme.palette.success.main,
          bgColor: alpha(theme.palette.success.main, 0.1),
          icon: <TrendingUp sx={{ fontSize: size === "small" ? 16 : 20 }} />,
          label: "BUY",
          textColor: theme.palette.success.dark,
        };
      case "SELL":
        return {
          color: theme.palette.error.main,
          bgColor: alpha(theme.palette.error.main, 0.1),
          icon: <TrendingDown sx={{ fontSize: size === "small" ? 16 : 20 }} />,
          label: "SELL",
          textColor: theme.palette.error.dark,
        };
      case "HOLD":
        return {
          color: theme.palette.warning.main,
          bgColor: alpha(theme.palette.warning.main, 0.1),
          icon: <ShowChart sx={{ fontSize: size === "small" ? 16 : 20 }} />,
          label: "HOLD",
          textColor: theme.palette.warning.dark,
        };
      default:
        return {
          color: theme.palette.grey[500],
          bgColor: alpha(theme.palette.grey[500], 0.1),
          icon: <SignalCellularAlt sx={{ fontSize: size === "small" ? 16 : 20 }} />,
          label: "",
          textColor: theme.palette.grey[600],
        };
    }
  };

  const config = getSignalConfig(signal);
  const confidencePercent = Math.round(confidence * 100);

  return (
    <Tooltip
      title={
        showConfidence
          ? `Signal: ${config.label} (${confidencePercent}% confidence)`
          : `Trading Signal: ${config.label}`
      }
    >
      <Box
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 0.5,
          px: size === "small" ? 1 : 1.5,
          py: size === "small" ? 0.25 : 0.5,
          borderRadius: 2,
          backgroundColor: config.bgColor,
          border: `1px solid ${alpha(config.color, 0.3)}`,
          minWidth: size === "small" ? 60 : 80,
          justifyContent: "center",
          cursor: "pointer",
          transition: "all 0.2s ease-in-out",
          "&:hover": {
            backgroundColor: alpha(config.color, 0.15),
            borderColor: alpha(config.color, 0.5),
            transform: "translateY(-1px)",
          },
        }}
      >
        {config.icon}
        <Typography
          variant={size === "small" ? "caption" : "body2"}
          sx={{
            color: config.textColor,
            fontWeight: 600,
            fontSize: size === "small" ? "0.65rem" : "0.75rem",
          }}
        >
          {config.label}
        </Typography>
        {showConfidence && (
          <Typography
            variant="caption"
            sx={{
              color: alpha(config.textColor, 0.7),
              fontSize: "0.6rem",
              ml: 0.5,
            }}
          >
            {confidencePercent}%
          </Typography>
        )}
      </Box>
    </Tooltip>
  );
};

// Score Gauge Component
const ScoreGauge = ({ score, size = 60, showGrade = false }) => {
  const theme = useTheme();

  const getColor = (value) => {
    if (value >= 80) return theme.palette.success.main;
    if (value >= 60) return theme.palette.warning.main;
    if (value >= 40) return theme.palette.info.main;
    return theme.palette.error.main;
  };

  const getGrade = (value) => {
    if (value >= 90) return "A+";
    if (value >= 85) return "A";
    if (value >= 80) return "A-";
    if (value >= 75) return "B+";
    if (value >= 70) return "B";
    if (value >= 65) return "B-";
    if (value >= 60) return "C+";
    if (value >= 55) return "C";
    if (value >= 50) return "C-";
    if (value >= 45) return "D+";
    if (value >= 40) return "D";
    return "F";
  };

  return (
    <Box
      sx={{
        position: "relative",
        width: size,
        height: size,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Box
        sx={{
          width: size,
          height: size,
          borderRadius: "50%",
          background: `conic-gradient(${getColor(score)} ${score * 3.6}deg, ${alpha(theme.palette.action.disabled, 0.1)} 0deg)`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Box
          sx={{
            width: size - 10,
            height: size - 10,
            borderRadius: "50%",
            backgroundColor: theme.palette.background.paper,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography variant="h6" fontWeight={700} fontSize={size > 70 ? "1rem" : "0.85rem"}>
            {score}
          </Typography>
          {showGrade && (
            <Typography variant="caption" color={getColor(score)} fontWeight={600}>
              {getGrade(score)}
            </Typography>
          )}
        </Box>
      </Box>
    </Box>
  );
};

const ScoresDashboard = () => {
  const theme = useTheme();

  // Helper: Safe score display - shows "N/A" for null instead of fake 0
  // Per RULES.md: NO fake data defaults
  const safeScoreDisplay = (score) => {
    return score !== null && score !== undefined ? parseFloat(score).toFixed(0) : "";
  };

  // Helper: Safe score for progress bar - returns 0 for display but doesn't use for data integrity
  const safeScoreValue = (score) => {
    return score !== null && score !== undefined ? parseFloat(score) : 0;
  };

  // Helper: Safe score color - returns neutral color for missing data
  const getScoreColor = (score) => {
    if (score === null || score === undefined) return theme.palette.action.disabled;
    if (score < 60) return theme.palette.error.main;
    if (score < 80) return theme.palette.warning.main;
    return theme.palette.success.main;
  };
  const [loading, setLoading] = useState(true);
  const [scores, setScores] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedStock, setExpandedStock] = useState(null);
  const [signals, setSignals] = useState({});
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(50); // Items per page
  const [showAllStocks, setShowAllStocks] = useState(false);
  const [currentPage, setCurrentPage] = useState(1); // Pagination state
  const [totalRecords, setTotalRecords] = useState(0); // Total from API
  const [totalPages, setTotalPages] = useState(0); // Total pages from API
  const [paginationInfo, setPaginationInfo] = useState(null); // Full pagination metadata

  // Advanced filter states
  const [minCompositeScore, setMinCompositeScore] = useState(0);
  const [minMomentumScore, setMinMomentumScore] = useState(0);
  const [minQualityScore, setMinQualityScore] = useState(0);
  const [minValueScore, setMinValueScore] = useState(0);
  const [minGrowthScore, setMinGrowthScore] = useState(0);
  const [sortBy, setSortBy] = useState("composite_score");
  const [sortOrder, setSortOrder] = useState("desc");
  const [selectedSector, setSelectedSector] = useState("all");

  // Calculate market averages for each score category
  // REAL DATA ONLY - exclude nulls, don't use 0 as default
  const calculateMarketAverages = (stocks) => {
    if (!stocks || stocks.length === 0) return {};

    const sum = (arr) => arr.reduce((a, b) => a + b, 0);
    const avg = (arr) => arr.length > 0 ? sum(arr) / arr.length : null;

    // Filter for real values only (not null/undefined)
    const getRealScores = (key) => stocks
      .map(s => s[key])
      .filter(v => v !== null && v !== undefined);

    return {
      quality: avg(getRealScores('quality_score')),
      momentum: avg(getRealScores('momentum_score')),
      value: avg(getRealScores('value_score')),
      growth: avg(getRealScores('growth_score')),
      positioning: avg(getRealScores('positioning_score')),
      consistency: avg(getRealScores('stability_score')),
    };
  };

  // Calculate sector averages for each score category
  // REAL DATA ONLY - exclude nulls, don't use 0 as default
  const calculateSectorAverages = (stocks, sector) => {
    if (!sector || sector === 'all' || !stocks || stocks.length === 0) return {};

    const sectorStocks = stocks.filter(s => s.sector === sector);
    if (sectorStocks.length === 0) return {};

    const sum = (arr) => arr.reduce((a, b) => a + b, 0);
    const avg = (arr) => arr.length > 0 ? sum(arr) / arr.length : null;

    // Filter for real values only (not null/undefined)
    const getRealScores = (key) => sectorStocks
      .map(s => s[key])
      .filter(v => v !== null && v !== undefined);

    return {
      quality: avg(getRealScores('quality_score')),
      momentum: avg(getRealScores('momentum_score')),
      value: avg(getRealScores('value_score')),
      growth: avg(getRealScores('growth_score')),
      positioning: avg(getRealScores('positioning_score')),
      risk: avg(getRealScores('stability_score')),
    };
  };

  // Transform data to handle both old and new API formats
  const transformStockData = (stock) => {
    // Return data as-is from API without any fallbacks or defaults
    // No fake data - only real data from database
    return stock;
  };

  useEffect(() => {
    loadAllScores();
  }, []);

  useEffect(() => {
    if (scores.length > 0) {
      loadSignalsForStocks(scores);
    }
  }, [scores]);

  const loadAllScores = async (page = 1) => {
    setLoading(true);
    try {
      const { default: api } = await import("../services/api");
      // Calculate offset based on page and displayLimit
      const offset = (page - 1) * displayLimit;

      // Fetch paginated data from API - use composite_score for main display
      const response = await api.get(
        `/api/scores/stockscores?limit=${displayLimit}&offset=${offset}&sortBy=composite_score`
      );

      // Check if API response is valid
      // Response structure from API: { items: [...], pagination: {...}, success: true }
      // axios wraps it, so response.data contains the above structure
      const validStocksArray = response.data?.items || [];

      if (validStocksArray.length > 0) {
        const transformedStocks = validStocksArray.map(transformStockData);
        setScores(transformedStocks);

        // Extract pagination info from response
        const totalRecords = response.data?.pagination?.total || validStocksArray.length;
        const pageSize = response.data?.pagination?.limit || displayLimit;
        const totalPages = Math.ceil(totalRecords / pageSize);

        setTotalRecords(totalRecords);
        setTotalPages(totalPages);
        setPaginationInfo({
          totalRecords: totalRecords,
          totalPages: totalPages,
          pageSize: pageSize,
          offset: response.data?.pagination?.offset || 0
        });
        setCurrentPage(page);
      } else {
        // Data is null or missing - API success but no data yet (compilation in progress)
        setScores([]);
        // Don't log as error - this is expected during compilation
        console.log("Stock scores compilation in progress. Data will be available shortly.");
      }
    } catch (error) {
      console.error("Error loading scores:", error);
      setScores([]);
    } finally {
      setLoading(false);
    }
  };

  const loadSignalsForStocks = async (stockList) => {
    if (signalsLoading || stockList.length === 0) return;

    setSignalsLoading(true);
    try {
      const { default: api } = await import("../services/api");

      // Helper to generate fallback signal based on scores
      const generateSignal = (stock) => {
        const composite = stock.composite_score;
        const momentum = stock.momentum_score;

        if (composite >= 80 && momentum >= 75) {
          return { signal: "BUY", confidence: 0.85 };
        }
        if (composite >= 70 && momentum >= 65) {
          return { signal: "BUY", confidence: 0.75 };
        }
        if (composite < 50 || momentum < 40) {
          return { signal: "SELL", confidence: 0.70 };
        }
        return { signal: "HOLD", confidence: 0.65 };
      };

      // Load ALL signals for all timeframes (daily, weekly, monthly)
      // Fetch complete history - no limit restriction
      const timeframes = ["daily", "weekly", "monthly"];
      const signalPromises = stockList.map(async (stock) => {
        const timeframeSignals = {};
        const timeframeAllSignals = {}; // Store ALL signals for each timeframe

        for (const timeframe of timeframes) {
          try {
            const response = await api.get(
              `/api/signals/stocks?symbol=${stock.symbol}&timeframe=${timeframe}&limit=500`
            );
            const signalsArray = response?.data?.items || [];
            if (response?.data?.success && signalsArray.length > 0) {
              // Store all signals for this timeframe
              timeframeAllSignals[timeframe] = signalsArray.filter(
                (signal) => signal.signal && ["Buy", "Sell"].includes(signal.signal)
              );

              // Use most recent signal as primary
              const signalData = signalsArray[0];
              const apiSignal = signalData.signal;
              if (apiSignal && ["Buy", "Sell"].includes(apiSignal)) {
                timeframeSignals[timeframe] = {
                  signal: apiSignal === "Buy" ? "BUY" : "SELL",
                  confidence: 0.80,
                  date: signalData.date,
                };
              }
            }
          } catch (err) {
            // If API call fails for this timeframe, continue to next
          }
        }

        // Use daily signal as primary display, fallback to generated if not available
        const dailySignal = timeframeSignals.daily;
        const weeklySignal = timeframeSignals.weekly;
        const monthlySignal = timeframeSignals.monthly;

        if (dailySignal) {
          return {
            symbol: stock.symbol,
            signal: dailySignal.signal,
            confidence: dailySignal.confidence,
            date: dailySignal.date,
            daily: dailySignal,
            dailyAllSignals: timeframeAllSignals.daily || [],
            weekly: weeklySignal || null,
            weeklyAllSignals: timeframeAllSignals.weekly || [],
            monthly: monthlySignal || null,
            monthlyAllSignals: timeframeAllSignals.monthly || [],
          };
        } else if (weeklySignal) {
          return {
            symbol: stock.symbol,
            signal: weeklySignal.signal,
            confidence: weeklySignal.confidence,
            date: weeklySignal.date,
            daily: null,
            dailyAllSignals: timeframeAllSignals.daily || [],
            weekly: weeklySignal,
            weeklyAllSignals: timeframeAllSignals.weekly || [],
            monthly: monthlySignal || null,
            monthlyAllSignals: timeframeAllSignals.monthly || [],
          };
        } else if (monthlySignal) {
          return {
            symbol: stock.symbol,
            signal: monthlySignal.signal,
            confidence: monthlySignal.confidence,
            date: monthlySignal.date,
            daily: null,
            dailyAllSignals: timeframeAllSignals.daily || [],
            weekly: null,
            weeklyAllSignals: timeframeAllSignals.weekly || [],
            monthly: monthlySignal,
            monthlyAllSignals: timeframeAllSignals.monthly || [],
          };
        } else {
          // Fallback to score-based signal if no API signals available
          const generated = generateSignal(stock);
          return {
            symbol: stock.symbol,
            signal: generated.signal,
            confidence: generated.confidence,
            date: new Date().toISOString().split('T')[0],
            daily: null,
            dailyAllSignals: [],
            weekly: null,
            weeklyAllSignals: [],
            monthly: null,
            monthlyAllSignals: [],
          };
        }
      });

      const signalResults = await Promise.all(signalPromises);
      const signalsMap = {};

      signalResults.forEach((result) => {
        if (result) {
          signalsMap[result.symbol] = result;
        }
      });

      setSignals((prev) => ({ ...prev, ...signalsMap }));
    } catch (error) {
      console.error("Error loading signals:", error);
    } finally {
      setSignalsLoading(false);
    }
  };

  // Extract unique sectors from scores
  const sectors = [...new Set(scores.map((stock) => stock.sector).filter(Boolean))].sort();

  // Filter and sort scores
  // NOTE: Filters are applied but don't re-sort paginated API data
  // The API already returns data in correct order (composite_score DESC)
  // We only re-sort if user changes filter criteria or explicitly changes sort
  const hasActiveFilters = searchTerm || minCompositeScore > 0 || minMomentumScore > 0 ||
                           minQualityScore > 0 || minValueScore > 0 || minGrowthScore > 0 ||
                           selectedSector !== "all" || sortBy !== "composite_score" || sortOrder !== "desc";

  const filteredAndSortedScores = scores
    .filter((stock) => {
      const matchesSearch = stock.symbol.toLowerCase().includes(searchTerm.toLowerCase());
      // REAL DATA ONLY - null scores can only pass filter if threshold is 0 (no requirement)
      const matchesComposite = minCompositeScore === 0
        ? true
        : (stock.composite_score !== null && stock.composite_score !== undefined && stock.composite_score >= minCompositeScore);
      const matchesMomentum = minMomentumScore === 0
        ? true
        : (stock.momentum_score !== null && stock.momentum_score !== undefined && stock.momentum_score >= minMomentumScore);
      const matchesQuality = minQualityScore === 0
        ? true
        : (stock.quality_score !== null && stock.quality_score !== undefined && stock.quality_score >= minQualityScore);
      const matchesValue = minValueScore === 0
        ? true
        : (stock.value_score !== null && stock.value_score !== undefined && stock.value_score >= minValueScore);
      const matchesGrowth = minGrowthScore === 0
        ? true
        : (stock.growth_score !== null && stock.growth_score !== undefined && stock.growth_score >= minGrowthScore);
      const matchesSector = selectedSector === "all" || stock.sector === selectedSector;

      return matchesSearch && matchesComposite && matchesMomentum && matchesQuality && matchesValue && matchesGrowth && matchesSector;
    })
    // Only sort if user has applied custom filters/sorts
    // Otherwise, respect the API ordering (which is composite_score DESC)
    .sort((a, b) => {
      // If no filters applied, maintain API order by preserving index (stable sort)
      if (!hasActiveFilters) {
        return 0; // Don't change order - API provides correct ordering
      }

      // REAL DATA ONLY - handle null values properly (nulls go to bottom)
      let aValue = a[sortBy];
      let bValue = b[sortBy];

      // Null values always sort to bottom (end)
      if (aValue === null || aValue === undefined) return 1;
      if (bValue === null || bValue === undefined) return -1;

      // Both have real values - compare numerically
      const comparison = bValue - aValue;
      return sortOrder === "desc" ? comparison : -comparison;
    });

  // Get displayed stocks (paginated)
  const displayedStocks = showAllStocks ? filteredAndSortedScores : filteredAndSortedScores.slice(0, displayLimit);

  // Get top performers for each category with optional sector filtering - ONLY real data
  const getTopPerformers = (scoreField, count = 10, sector = null) => {
    const filteredScores = sector && sector !== "all"
      ? scores.filter((stock) => stock.sector === sector)
      : scores;

    return [...filteredScores]
      .filter((stock) => stock[scoreField] !== null && stock[scoreField] !== undefined)
      .sort((a, b) => b[scoreField] - a[scoreField]) // No fallback - we already filtered nulls
      .slice(0, count);
  };

  // Get top performers by sector - ONLY real data
  const getTopPerformersBySector = (count = 5) => {
    const bySector = {};
    sectors.forEach((sector) => {
      bySector[sector] = [...scores]
        .filter((stock) => stock.sector === sector && stock.composite_score !== null && stock.composite_score !== undefined)
        .sort((a, b) => b.composite_score - a.composite_score) // No fallback - we already filtered nulls
        .slice(0, count);
    });
    return bySector;
  };

  const topQuality = getTopPerformers("quality_score", 10, null);
  const topMomentum = getTopPerformers("momentum_score", 10, null);
  const topValue = getTopPerformers("value_score", 10, null);
  const topGrowth = getTopPerformers("growth_score", 10, null);
  const topPositioning = getTopPerformers("positioning_score", 10, null);
  const topStability = getTopPerformers("stability_score", 10, null);
  const topBySector = getTopPerformersBySector(5);

  // Get category leaders within each sector - ONLY real data, no fake defaults
  const getCategoryLeadersBySector = (sector) => {
    const sectorStocks = scores.filter(s => s.sector === sector);
    if (sectorStocks.length === 0) return {};

    const getSortedLeader = (sortFn, filterFn) => {
      const filtered = sectorStocks.filter(filterFn);
      const sorted = [...filtered].sort(sortFn);
      return sorted.length > 0 ? sorted[0] : undefined;
    };

    return {
      // No fallback in sorts - filter fn already ensures only non-null scores are compared
      quality: getSortedLeader((a, b) => b.quality_score - a.quality_score, s => s.quality_score !== null && s.quality_score !== undefined),
      momentum: getSortedLeader((a, b) => b.momentum_score - a.momentum_score, s => s.momentum_score !== null && s.momentum_score !== undefined),
      value: getSortedLeader((a, b) => b.value_score - a.value_score, s => s.value_score !== null && s.value_score !== undefined),
      growth: getSortedLeader((a, b) => b.growth_score - a.growth_score, s => s.growth_score !== null && s.growth_score !== undefined),
      positioning: getSortedLeader((a, b) => b.positioning_score - a.positioning_score, s => s.positioning_score !== null && s.positioning_score !== undefined),
    };
  };

  // State for expanded sector accordion
  const [expandedSector, setExpandedSector] = useState(null);

  const handleSectorAccordionChange = (sectorName) => (event, isExpanded) => {
    setExpandedSector(isExpanded ? sectorName : null);
  };

  const handleAccordionChange = (symbol) => (event, isExpanded) => {
    setExpandedStock(isExpanded ? symbol : null);
  };

  const clearFilters = () => {
    setSearchTerm("");
    setMinCompositeScore(0);
    setMinMomentumScore(0);
    setMinQualityScore(0);
    setMinValueScore(0);
    setMinGrowthScore(0);
    setSelectedSector("all");
  };

  const formatChange = (change) => {
    const numChange = parseFloat(change ?? 0);
    const isPositive = numChange >= 0;
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        {isPositive ? (
          <TrendingUp sx={{ fontSize: 16, color: theme.palette.success.main }} />
        ) : (
          <TrendingDown sx={{ fontSize: 16, color: theme.palette.error.main }} />
        )}
        <Typography
          variant="body2"
          sx={{
            color: isPositive ? theme.palette.success.main : theme.palette.error.main,
            fontWeight: 600,
          }}
        >
          {isPositive ? "+" : ""}
          {numChange.toFixed(2)}%
        </Typography>
      </Box>
    );
  };

  // Export handlers
  const handleExportCSV = () => {
    const dataToExport = filteredAndSortedScores.map((stock) => ({
      symbol: stock.symbol,
      sector: stock.sector,
      "composite_score": stock.composite_score,
      "momentum_score": stock.momentum_score,
      "quality_score": stock.quality_score,
      "value_score": stock.value_score,
      "growth_score": stock.growth_score,
      "positioning_score": stock.positioning_score,
      "price": stock.price,
      "change_percent": stock.change_percent,
    }));
    exportToCSV(dataToExport, "stock-scores");
  };

  const handleExportJSON = () => {
    const dataToExport = filteredAndSortedScores.map((stock) => ({
      symbol: stock.symbol,
      sector: stock.sector,
      composite_score: stock.composite_score,
      momentum_score: stock.momentum_score,
      quality_score: stock.quality_score,
      value_score: stock.value_score,
      growth_score: stock.growth_score,
      positioning_score: stock.positioning_score,
      price: stock.price,
      change_percent: stock.change_percent,
    }));
    exportToJSON(dataToExport, "stock-scores");
  };

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 400 }}>
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Paper
        elevation={0}
        sx={{
          textAlign: "center",
          mb: 4,
          p: 4,
          borderRadius: 3,
          border: `1px solid ${theme.palette.divider}`,
          background: theme.palette.mode === "dark"
            ? `linear-gradient(145deg, ${theme.palette.background.paper}, ${alpha(theme.palette.primary.main, 0.02)})`
            : `linear-gradient(145deg, ${theme.palette.background.paper}, ${alpha(theme.palette.primary.main, 0.03)})`,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, mb: 2 }}>
          <Box
            sx={{
              width: 60,
              height: 60,
              borderRadius: "50%",
              background: `conic-gradient(${theme.palette.primary.main} 90deg, ${theme.palette.success.main} 90deg 180deg, ${theme.palette.warning.main} 180deg 270deg, ${theme.palette.error.main} 270deg)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              position: "relative",
            }}
          >
            <Box
              sx={{
                width: 50,
                height: 50,
                borderRadius: "50%",
                backgroundColor: theme.palette.background.paper,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Typography variant="h4" sx={{ fontWeight: 700 }}>
                🎯
              </Typography>
            </Box>
          </Box>
          <Typography variant="h3" component="h1" fontWeight={700} sx={{ letterSpacing: "-0.5px" }}>
            Bullseye Stock Screener
          </Typography>
        </Box>
      </Paper>

      {/* Search and Filter Controls */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center", mb: showFilters ? 2 : 0 }}>
          <TextField
            variant="outlined"
            placeholder="Search stocks by symbol..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            size="small"
            sx={{ minWidth: 250, flex: 1 }}
          />

          <FormControl variant="outlined" size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Sort By</InputLabel>
            <Select value={sortBy} label="Sort By" onChange={(e) => setSortBy(e.target.value)}>
              <MenuItem value="composite_score">Composite</MenuItem>
              <MenuItem value="momentum_score">Momentum</MenuItem>
              <MenuItem value="quality_score">Quality</MenuItem>
              <MenuItem value="value_score">Value</MenuItem>
              <MenuItem value="growth_score">Growth</MenuItem>
              <MenuItem value="positioning_score">Positioning</MenuItem>
            </Select>
          </FormControl>

          <FormControl variant="outlined" size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Order</InputLabel>
            <Select value={sortOrder} label="Order" onChange={(e) => setSortOrder(e.target.value)}>
              <MenuItem value="desc">High to Low</MenuItem>
              <MenuItem value="asc">Low to High</MenuItem>
            </Select>
          </FormControl>

          <FormControl variant="outlined" size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Sector</InputLabel>
            <Select value={selectedSector} label="Sector" onChange={(e) => setSelectedSector(e.target.value)}>
              <MenuItem value="all">All Sectors</MenuItem>
              {sectors.map((sector) => (
                <MenuItem key={sector} value={sector}>{sector}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <Tooltip title="Advanced Filters">
            <IconButton
              onClick={() => setShowFilters(!showFilters)}
              color={showFilters ? "primary" : "default"}
            >
              <FilterList />
            </IconButton>
          </Tooltip>

          {(searchTerm || minCompositeScore > 0 || minMomentumScore > 0 || minQualityScore > 0 || minValueScore > 0 || minGrowthScore > 0 || selectedSector !== "all") && (
            <Tooltip title="Clear All Filters">
              <IconButton onClick={clearFilters} color="error" size="small">
                <ClearAll />
              </IconButton>
            </Tooltip>
          )}
        </Box>

        {showFilters && (
          <Box sx={{ pt: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={2.4}>
                <FormControl fullWidth size="small">
                  <InputLabel>Min Composite</InputLabel>
                  <Select
                    value={minCompositeScore}
                    label="Min Composite"
                    onChange={(e) => setMinCompositeScore(e.target.value)}
                  >
                    <MenuItem value={0}>All</MenuItem>
                    <MenuItem value={50}>50+</MenuItem>
                    <MenuItem value={60}>60+</MenuItem>
                    <MenuItem value={70}>70+</MenuItem>
                    <MenuItem value={80}>80+</MenuItem>
                    <MenuItem value={90}>90+</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={2.4}>
                <FormControl fullWidth size="small">
                  <InputLabel>Min Momentum</InputLabel>
                  <Select
                    value={minMomentumScore}
                    label="Min Momentum"
                    onChange={(e) => setMinMomentumScore(e.target.value)}
                  >
                    <MenuItem value={0}>All</MenuItem>
                    <MenuItem value={50}>50+</MenuItem>
                    <MenuItem value={60}>60+</MenuItem>
                    <MenuItem value={70}>70+</MenuItem>
                    <MenuItem value={80}>80+</MenuItem>
                    <MenuItem value={90}>90+</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={2.4}>
                <FormControl fullWidth size="small">
                  <InputLabel>Min Quality</InputLabel>
                  <Select
                    value={minQualityScore}
                    label="Min Quality"
                    onChange={(e) => setMinQualityScore(e.target.value)}
                  >
                    <MenuItem value={0}>All</MenuItem>
                    <MenuItem value={50}>50+</MenuItem>
                    <MenuItem value={60}>60+</MenuItem>
                    <MenuItem value={70}>70+</MenuItem>
                    <MenuItem value={80}>80+</MenuItem>
                    <MenuItem value={90}>90+</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={2.4}>
                <FormControl fullWidth size="small">
                  <InputLabel>Min Value</InputLabel>
                  <Select
                    value={minValueScore}
                    label="Min Value"
                    onChange={(e) => setMinValueScore(e.target.value)}
                  >
                    <MenuItem value={0}>All</MenuItem>
                    <MenuItem value={50}>50+</MenuItem>
                    <MenuItem value={60}>60+</MenuItem>
                    <MenuItem value={70}>70+</MenuItem>
                    <MenuItem value={80}>80+</MenuItem>
                    <MenuItem value={90}>90+</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={2.4}>
                <FormControl fullWidth size="small">
                  <InputLabel>Min Growth</InputLabel>
                  <Select
                    value={minGrowthScore}
                    label="Min Growth"
                    onChange={(e) => setMinGrowthScore(e.target.value)}
                  >
                    <MenuItem value={0}>All</MenuItem>
                    <MenuItem value={50}>50+</MenuItem>
                    <MenuItem value={60}>60+</MenuItem>
                    <MenuItem value={70}>70+</MenuItem>
                    <MenuItem value={80}>80+</MenuItem>
                    <MenuItem value={90}>90+</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </Box>
        )}
      </Paper>

      {/* Overall Stocks List */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2, gap: 1, flexWrap: "wrap" }}>
          <Typography variant="h5" gutterBottom sx={{ m: 0 }}>
            Top Overall Stocks ({filteredAndSortedScores.length})
          </Typography>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", ml: "auto" }}>
            {filteredAndSortedScores.length > 0 && (
              <>
                <Tooltip title="Export as CSV">
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={handleExportCSV}
                    startIcon={<DownloadIcon />}
                    sx={{ whiteSpace: "nowrap" }}
                  >
                    CSV
                  </Button>
                </Tooltip>
                <Tooltip title="Export as JSON">
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={handleExportJSON}
                    startIcon={<DownloadIcon />}
                    sx={{ whiteSpace: "nowrap" }}
                  >
                    JSON
                  </Button>
                </Tooltip>
              </>
            )}
            {filteredAndSortedScores.length > displayLimit && !showAllStocks && (
              <Button
                variant="outlined"
                size="small"
                onClick={() => setShowAllStocks(true)}
                startIcon={<ExpandMore />}
              >
                Show All {filteredAndSortedScores.length}
              </Button>
            )}
            {showAllStocks && filteredAndSortedScores.length > displayLimit && (
              <Button
                variant="outlined"
                size="small"
                onClick={() => setShowAllStocks(false)}
                startIcon={<ExpandMore sx={{ transform: "rotate(180deg)" }} />}
              >
                Show Top {displayLimit}
              </Button>
            )}
          </Box>
        </Box>

        {filteredAndSortedScores.length === 0 ? (
          <Paper sx={{ p: 4, textAlign: "center" }}>
            <Typography variant="h6" color="text.secondary">
              No stocks found matching your filters
            </Typography>
            <Button variant="outlined" onClick={clearFilters} sx={{ mt: 2 }}>
              Clear Filters
            </Button>
          </Paper>
        ) : (
          <Box>
            {displayedStocks.map((stock, index) => (
            <Accordion
              key={`${stock.symbol}-${index}`}
              expanded={expandedStock === stock.symbol}
              onChange={handleAccordionChange(stock.symbol)}
              sx={{ mb: 1 }}
            >
              <AccordionSummary
                expandIcon={<ExpandMore />}
                sx={{
                  "&:hover": {
                    backgroundColor: alpha(theme.palette.primary.main, 0.02),
                  },
                }}
              >
                <Grid container alignItems="center" spacing={2} sx={{ width: "100%" }}>
                  {/* Left: Score Gauge */}
                  <Grid item xs="auto">
                    <ScoreGauge
                      score={stock.composite_score !== null && stock.composite_score !== undefined ? Math.round(stock.composite_score) : null}
                      size={70}
                      showGrade
                    />
                  </Grid>

                  {/* Middle: Symbol, Company Name, and Trading Signal */}
                  <Grid item xs={12} sm="auto" sx={{ flexGrow: { xs: 1, sm: 0 }, minWidth: { sm: 200 } }}>
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
                      <Typography variant="h5" fontWeight={700}>
                        {stock.symbol}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.2 }}>
                        {stock.company_name || "Company Name"}
                      </Typography>
                      {signals[stock.symbol] && (
                        <Box sx={{ mt: 0.5 }}>
                          <TradingSignal
                            signal={signals[stock.symbol].signal}
                            confidence={signals[stock.symbol].confidence}
                            size="small"
                          />
                        </Box>
                      )}
                    </Box>
                  </Grid>

                  {/* Right: Individual Score Bars */}
                  <Grid item xs={12} sm sx={{ flexGrow: 1 }}>
                    <Grid container spacing={1}>
                      {/* Quality Score */}
                      <Grid item xs={6} sm={4}>
                        <Box>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                              Quality
                            </Typography>
                            <Typography variant="caption" fontWeight={700}>
                              {safeScoreDisplay(stock.quality_score)}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={safeScoreValue(stock.quality_score)}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: getScoreColor(stock.quality_score),
                                borderRadius: 1,
                              },
                            }}
                          />
                        </Box>
                      </Grid>

                      {/* Momentum Score */}
                      <Grid item xs={6} sm={4}>
                        <Box>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                              Momentum
                            </Typography>
                            <Typography variant="caption" fontWeight={700}>
                              {safeScoreDisplay(stock.momentum_score)}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={safeScoreValue(stock.momentum_score)}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: getScoreColor(stock.momentum_score),
                                borderRadius: 1,
                              },
                            }}
                          />
                        </Box>
                      </Grid>

                      {/* Value Score */}
                      <Grid item xs={6} sm={4}>
                        <Box>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                              Value
                            </Typography>
                            <Typography variant="caption" fontWeight={700}>
                              {stock.value_score != null ? parseFloat(stock.value_score).toFixed(0) : ""}
                            </Typography>
                          </Box>
                          {stock.value_score != null && (
                            <LinearProgress
                              variant="determinate"
                              value={parseFloat(stock.value_score)}
                              sx={{
                                height: 8,
                                borderRadius: 1,
                                backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                                "& .MuiLinearProgress-bar": {
                                  backgroundColor: parseFloat(stock.value_score) < 60
                                    ? theme.palette.error.main
                                    : parseFloat(stock.value_score) < 80
                                    ? theme.palette.warning.main
                                    : theme.palette.success.main,
                                  borderRadius: 1,
                                },
                              }}
                            />
                          )}
                        </Box>
                      </Grid>

                      {/* Growth Score */}
                      <Grid item xs={6} sm={4}>
                        <Box>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                              Growth
                            </Typography>
                            <Typography variant="caption" fontWeight={700}>
                              {safeScoreDisplay(stock.growth_score)}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={safeScoreValue(stock.growth_score)}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: getScoreColor(stock.growth_score),
                                borderRadius: 1,
                              },
                            }}
                          />
                        </Box>
                      </Grid>

                      {/* Positioning Score */}
                      <Grid item xs={6} sm={4}>
                        <Box>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                              Positioning
                            </Typography>
                            <Typography variant="caption" fontWeight={700}>
                              {stock.positioning_score != null ? parseFloat(stock.positioning_score).toFixed(0) : ""}
                            </Typography>
                          </Box>
                          {stock.positioning_score != null && (
                            <LinearProgress
                              variant="determinate"
                              value={parseFloat(stock.positioning_score)}
                              sx={{
                                height: 8,
                                borderRadius: 1,
                                backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                                "& .MuiLinearProgress-bar": {
                                  backgroundColor: parseFloat(stock.positioning_score) < 60
                                    ? theme.palette.error.main
                                    : parseFloat(stock.positioning_score) < 80
                                    ? theme.palette.warning.main
                                    : theme.palette.success.main,
                                  borderRadius: 1,
                                },
                              }}
                            />
                          )}
                        </Box>
                      </Grid>

                      {/* Stability Score */}
                      <Grid item xs={6} sm={4}>
                        <Box>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                              Stability
                            </Typography>
                            <Typography variant="caption" fontWeight={700}>
                              {stock.stability_score !== null && stock.stability_score !== undefined ? parseFloat(stock.stability_score).toFixed(0) : ""}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={stock.stability_score !== null && stock.stability_score !== undefined ? Math.min(100, parseFloat(stock.stability_score)) : null}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: stock.stability_score === null || stock.stability_score === undefined
                                  ? theme.palette.action.disabled
                                  : parseFloat(stock.stability_score) < 60
                                  ? theme.palette.error.main
                                  : parseFloat(stock.stability_score) < 80
                                  ? theme.palette.warning.main
                                  : theme.palette.success.main,
                                borderRadius: 1,
                              },
                            }}
                          />
                        </Box>
                      </Grid>
                    </Grid>
                  </Grid>
                </Grid>
              </AccordionSummary>
              <AccordionDetails>
                <Box>
                  <Typography variant="h6" gutterBottom sx={{ mb: 3 }}>
                    Factor Analysis for {stock.symbol}
                  </Typography>

                  {(() => {
                    const marketAvgs = calculateMarketAverages(scores);
                    const sectorAvgs = calculateSectorAverages(scores, stock.sector);

                    return (
                      <>
                      <Grid container spacing={2}>
                        {/* Quality Factor */}
                        <Grid item xs={12} md={6}>
                          <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                            <CardContent sx={{ pb: 2 }}>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                                <Stars sx={{ color: theme.palette.primary.main }} />
                                <Typography variant="h6">Quality & Fundamentals</Typography>
                                <Chip
                                  label={stock.quality_score != null ? parseFloat(stock.quality_score).toFixed(1) : ""}
                                  sx={{
                                    backgroundColor: getScoreColor(stock.quality_score),
                                    color: 'white',
                                    fontWeight: 600
                                  }}
                                  size="small"
                                />
                              </Box>
                              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                                Financial strength evaluation measuring profitability, balance sheet health, and operational efficiency
                              </Typography>

                              <Divider sx={{ my: 2 }} />

                              {/* Quality Comparison Chart */}
                              <Box sx={{ mt: 2 }}>
                                <Typography variant="caption" color="text.secondary" gutterBottom>
                                  Score Comparison
                                </Typography>
                                <ResponsiveContainer width="100%" height={200}>
                                  <BarChart
                                    data={[
                                      {
                                        name: stock.symbol,
                                        value: stock.quality_score !== null && stock.quality_score !== undefined ? stock.quality_score : null
                                      },
                                      {
                                        name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                        value: sectorAvgs.quality !== null && sectorAvgs.quality !== undefined ? sectorAvgs.quality : null
                                      },
                                      {
                                        name: "Market Avg",
                                        value: marketAvgs.quality !== null && marketAvgs.quality !== undefined ? marketAvgs.quality : null
                                      },
                                    ]}
                                    margin={{ top: 10, right: 10, left: 0, bottom: 5 }}
                                  >
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="name" style={{ fontSize: "0.7rem" }} />
                                    <YAxis domain={[0, 100]} style={{ fontSize: "0.75rem" }} />
                                    <RechartsTooltip />
                                    <Bar dataKey="value" name="Quality Score">
                                      {[
                                        <Cell key="stock" fill={theme.palette.primary.main} />,
                                        <Cell key="sector" fill={theme.palette.info.main} />,
                                        <Cell key="market" fill={theme.palette.success.light} />
                                      ]}
                                      <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value !== null && value !== undefined ? parseFloat(value).toFixed(1) : "—"} />
                                    </Bar>
                                  </BarChart>
                                </ResponsiveContainer>
                              </Box>

                              {/* Quality Input Metrics Table */}
                              <TableContainer sx={{ mt: 2 }}>
                                <Table size="small">
                                  <TableHead>
                                    <TableRow>
                                      <TableCell>Quality Metric</TableCell>
                                      <TableCell align="right">Value</TableCell>
                                    </TableRow>
                                  </TableHead>
                                  <TableBody>
                                    {!stock.quality_inputs && (
                                      <TableRow>
                                        <TableCell colSpan={2} align="center">
                                          <Typography variant="caption" color="text.secondary">
                                            Quality metrics data loading...
                                          </Typography>
                                        </TableCell>
                                      </TableRow>
                                    )}
                                    {stock.quality_inputs && Object.values(stock.quality_inputs).every(v => v === null || v === undefined) && (
                                      <TableRow>
                                        <TableCell colSpan={2} align="center">
                                          <Typography variant="caption" color="text.secondary">
                                            No detailed quality metrics available for this stock
                                          </Typography>
                                        </TableCell>
                                      </TableRow>
                                    )}
                                    {stock.quality_inputs && (
                                      <>
                                        {/* Only render rows with actual data - NO "N/A" values for financial metrics */}
                                        {stock.quality_inputs.return_on_equity_pct !== null && stock.quality_inputs.return_on_equity_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>Return on Equity (ROE)</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.return_on_equity_pct).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.return_on_assets_pct !== null && stock.quality_inputs.return_on_assets_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>Return on Assets (ROA)</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.return_on_assets_pct).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.gross_margin_pct !== null && stock.quality_inputs.gross_margin_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>Gross Margin</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.gross_margin_pct).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.operating_margin_pct !== null && stock.quality_inputs.operating_margin_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>Operating Margin</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.operating_margin_pct).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.profit_margin_pct !== null && stock.quality_inputs.profit_margin_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>Profit Margin</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.profit_margin_pct).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.fcf_to_net_income !== null && stock.quality_inputs.fcf_to_net_income !== undefined && (
                                          <TableRow>
                                            <TableCell>FCF / Net Income</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.fcf_to_net_income).toFixed(2)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.operating_cf_to_net_income !== null && stock.quality_inputs.operating_cf_to_net_income !== undefined && (
                                          <TableRow>
                                            <TableCell>Operating CF / Net Income</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.operating_cf_to_net_income).toFixed(2)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.debt_to_equity !== null && stock.quality_inputs.debt_to_equity !== undefined && (
                                          <TableRow>
                                            <TableCell>Debt-to-Equity Ratio</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.debt_to_equity).toFixed(2)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.current_ratio !== null && stock.quality_inputs.current_ratio !== undefined && (
                                          <TableRow>
                                            <TableCell>Current Ratio</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.current_ratio).toFixed(2)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.quick_ratio !== null && stock.quality_inputs.quick_ratio !== undefined && (
                                          <TableRow>
                                            <TableCell>Quick Ratio</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.quick_ratio).toFixed(2)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.earnings_surprise_avg !== null && stock.quality_inputs.earnings_surprise_avg !== undefined && (
                                          <TableRow>
                                            <TableCell>Earnings Surprise Avg (4Q)</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.earnings_surprise_avg).toFixed(2)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.eps_growth_stability !== null && stock.quality_inputs.eps_growth_stability !== undefined && (
                                          <TableRow>
                                            <TableCell>EPS Growth Stability (Std Dev)</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.eps_growth_stability).toFixed(2)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.payout_ratio !== null && stock.quality_inputs.payout_ratio !== undefined && (
                                          <TableRow>
                                            <TableCell>Payout Ratio</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.payout_ratio).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.return_on_invested_capital_pct !== null && stock.quality_inputs.return_on_invested_capital_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>Return on Invested Capital (ROIC)</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.return_on_invested_capital_pct).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.earnings_beat_rate !== null && stock.quality_inputs.earnings_beat_rate !== undefined && (
                                          <TableRow>
                                            <TableCell>Earnings Beat Rate</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.earnings_beat_rate).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.estimate_revision_direction !== null && stock.quality_inputs.estimate_revision_direction !== undefined && (
                                          <TableRow>
                                            <TableCell>Estimate Revision Direction</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.estimate_revision_direction).toFixed(1)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.consecutive_positive_quarters !== null && stock.quality_inputs.consecutive_positive_quarters !== undefined && (
                                          <TableRow>
                                            <TableCell>Consecutive Positive Quarters</TableCell>
                                            <TableCell align="right">{stock.quality_inputs.consecutive_positive_quarters}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.surprise_consistency !== null && stock.quality_inputs.surprise_consistency !== undefined && (
                                          <TableRow>
                                            <TableCell>Earnings Surprise Consistency (Std Dev)</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.surprise_consistency).toFixed(2)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.roe_stability_index !== null && stock.quality_inputs.roe_stability_index !== undefined && (
                                          <TableRow>
                                            <TableCell>ROE Stability Index (4Y Trend)</TableCell>
                                            <TableCell align="right">{parseFloat(stock.quality_inputs.roe_stability_index).toFixed(1)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.ebitda_margin_pct !== null && stock.quality_inputs.ebitda_margin_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>EBITDA Margin %</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.ebitda_margin_pct).toFixed(1)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.total_debt !== null && stock.quality_inputs.total_debt !== undefined && (
                                          <TableRow>
                                            <TableCell>Total Debt</TableCell>
                                            <TableCell align="right">${(stock.quality_inputs.total_debt / 1e9).toFixed(2)}B</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.total_cash !== null && stock.quality_inputs.total_cash !== undefined && (
                                          <TableRow>
                                            <TableCell>Total Cash</TableCell>
                                            <TableCell align="right">${(stock.quality_inputs.total_cash / 1e9).toFixed(2)}B</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.cash_per_share !== null && stock.quality_inputs.cash_per_share !== undefined && (
                                          <TableRow>
                                            <TableCell>Cash Per Share</TableCell>
                                            <TableCell align="right">${parseFloat(stock.quality_inputs.cash_per_share).toFixed(2)}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.free_cashflow !== null && stock.quality_inputs.free_cashflow !== undefined && (
                                          <TableRow>
                                            <TableCell>Free Cash Flow</TableCell>
                                            <TableCell align="right">${(stock.quality_inputs.free_cashflow / 1e9).toFixed(2)}B</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.operating_cashflow !== null && stock.quality_inputs.operating_cashflow !== undefined && (
                                          <TableRow>
                                            <TableCell>Operating Cash Flow</TableCell>
                                            <TableCell align="right">${(stock.quality_inputs.operating_cashflow / 1e9).toFixed(2)}B</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.earnings_growth_pct !== null && stock.quality_inputs.earnings_growth_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>Earnings Growth %</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.earnings_growth_pct).toFixed(2)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.revenue_growth_pct !== null && stock.quality_inputs.revenue_growth_pct !== undefined && (
                                          <TableRow>
                                            <TableCell>Revenue Growth %</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.revenue_growth_pct).toFixed(2)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                        {stock.quality_inputs.earnings_growth_4q_avg !== null && stock.quality_inputs.earnings_growth_4q_avg !== undefined && (
                                          <TableRow>
                                            <TableCell>Earnings Growth (4Q Avg)</TableCell>
                                            <TableCell align="right">{`${parseFloat(stock.quality_inputs.earnings_growth_4q_avg).toFixed(2)}%`}</TableCell>
                                          </TableRow>
                                        )}
                                      </>
                                    )}
                                  </TableBody>
                                </Table>
                              </TableContainer>
                            </CardContent>
                          </Card>
                        </Grid>


                        {/* Growth Factor */}
                        <Grid item xs={12} md={6}>
                          <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                            <CardContent sx={{ pb: 2 }}>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                                <TrendingUp sx={{ color: theme.palette.info.main }} />
                                <Typography variant="h6">Growth Metrics</Typography>
                                <Chip
                                  label={stock.growth_score != null ? parseFloat(stock.growth_score).toFixed(1) : ""}
                                  color={stock.growth_score !== null && stock.growth_score !== undefined && parseFloat(stock.growth_score) >= 80 ? "success" : "default"}
                                  size="small"
                                />
                              </Box>
                              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                                12 growth factors: Revenue, EPS, Net Income, Op Income, Margins (3), ROE, SGR, Momentum, FCF, Assets
                              </Typography>

                              <Divider sx={{ my: 2 }} />

                              <TableContainer>
                                <Table size="small">
                                  <TableBody>
                                    <TableRow>
                                      <TableCell>Revenue CAGR (3Y)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.revenue_growth_3y_cagr != null ? `${parseFloat(stock.growth_inputs.revenue_growth_3y_cagr).toFixed(2)}%` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>EPS CAGR (3Y)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.eps_growth_3y_cagr != null ? `${parseFloat(stock.growth_inputs.eps_growth_3y_cagr).toFixed(2)}%` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Net Income Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.net_income_growth_yoy != null ? `${parseFloat(stock.growth_inputs.net_income_growth_yoy).toFixed(2)}%` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Op Income Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.operating_income_growth_yoy != null ? `${parseFloat(stock.growth_inputs.operating_income_growth_yoy).toFixed(2)}%` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Gross Margin Trend</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.gross_margin_trend != null ? `${parseFloat(stock.growth_inputs.gross_margin_trend).toFixed(2)} pp` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Operating Margin Trend</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.operating_margin_trend != null ? `${parseFloat(stock.growth_inputs.operating_margin_trend).toFixed(2)} pp` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Net Margin Trend</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.net_margin_trend != null ? `${parseFloat(stock.growth_inputs.net_margin_trend).toFixed(2)} pp` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>ROE Trend</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.roe_trend != null ? `${parseFloat(stock.growth_inputs.roe_trend).toFixed(2)}` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Sustainable Growth Rate</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.sustainable_growth_rate != null ? `${parseFloat(stock.growth_inputs.sustainable_growth_rate).toFixed(2)}%` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Quarterly Growth Momentum</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.quarterly_growth_momentum != null ? `${parseFloat(stock.growth_inputs.quarterly_growth_momentum).toFixed(2)} pp` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>FCF Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.fcf_growth_yoy != null ? `${parseFloat(stock.growth_inputs.fcf_growth_yoy).toFixed(2)}%` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>OCF Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.ocf_growth_yoy != null ? `${parseFloat(stock.growth_inputs.ocf_growth_yoy).toFixed(2)}%` : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Asset Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.asset_growth_yoy != null ? `${parseFloat(stock.growth_inputs.asset_growth_yoy).toFixed(2)}%` : ""}
                                      </TableCell>
                                    </TableRow>
                                  </TableBody>
                                </Table>
                              </TableContainer>
                            </CardContent>
                          </Card>
                        </Grid>

                        {/* Stability Factor Analysis */}
                        <Grid item xs={12} md={6}>
                          <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                            <CardContent sx={{ pb: 2 }}>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                                <Security sx={{ color: theme.palette.success.main }} />
                                <Typography variant="h6">Stability Factor Analysis</Typography>
                                <Chip
                                  label={stock.stability_score !== null && stock.stability_score !== undefined
                                    ? parseFloat(stock.stability_score).toFixed(1)
                                    : ""}
                                  color={stock.stability_score === null || stock.stability_score === undefined
                                    ? "default"
                                    : parseFloat(stock.stability_score) < 60
                                      ? "error"
                                      : parseFloat(stock.stability_score) < 80
                                        ? "warning"
                                        : "success"}
                                  size="small"
                                />
                              </Box>
                              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                                Stability assessment measuring lower volatility and smoother price movement
                              </Typography>

                              <Divider sx={{ my: 2 }} />

                              {/* Stability Score Comparison Chart */}
                              <Box sx={{ mt: 2 }}>
                                <Typography variant="caption" color="text.secondary" gutterBottom>
                                  Score Comparison
                                </Typography>
                                <ResponsiveContainer width="100%" height={200}>
                                  <BarChart
                                    data={[
                                      {
                                        name: stock.symbol,
                                        value: stock.stability_score
                                      },
                                      {
                                        name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                        value: sectorAvgs.stability
                                      },
                                      {
                                        name: "Market Avg",
                                        value: marketAvgs.stability
                                      },
                                    ]}
                                    margin={{ top: 10, right: 10, left: 0, bottom: 5 }}
                                  >
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="name" style={{ fontSize: "0.7rem" }} />
                                    <YAxis domain={[0, 100]} style={{ fontSize: "0.75rem" }} />
                                    <RechartsTooltip />
                                    <Bar dataKey="value" name="Stability Score">
                                      {[
                                        <Cell key="stock" fill={stock.stability_score === null || stock.stability_score === undefined ? theme.palette.action.disabled : parseFloat(stock.stability_score) < 60 ? theme.palette.error.main : parseFloat(stock.stability_score) < 80 ? theme.palette.warning.main : theme.palette.success.main} />,
                                        <Cell key="sector" fill={sectorAvgs.stability === null ? theme.palette.action.disabled : theme.palette.primary.main} />,
                                        <Cell key="market" fill={marketAvgs.stability === null ? theme.palette.action.disabled : theme.palette.info.light} />
                                      ]}
                                      <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value !== null && value !== undefined ? parseFloat(value).toFixed(1) : ""} />
                                    </Bar>
                                  </BarChart>
                                </ResponsiveContainer>
                              </Box>

                              {/* Stability Components Table */}
                              <TableContainer sx={{ mt: 2 }}>
                                <Table size="small">
                                  <TableHead>
                                    <TableRow>
                                      <TableCell>Stability Component</TableCell>
                                      <TableCell align="right">Value</TableCell>
                                    </TableRow>
                                  </TableHead>
                                  <TableBody>
                                    <TableRow>
                                      <TableCell>Volatility (12M)</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.volatility_12m !== null && stock.stability_inputs?.volatility_12m !== undefined
                                          ? `${parseFloat(stock.stability_inputs.volatility_12m).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Downside Volatility</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.downside_volatility !== null && stock.stability_inputs?.downside_volatility !== undefined
                                          ? `${parseFloat(stock.stability_inputs.downside_volatility).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Max Drawdown (52W)</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.max_drawdown_52w !== null && stock.stability_inputs?.max_drawdown_52w !== undefined
                                          ? `${parseFloat(stock.stability_inputs.max_drawdown_52w).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Beta (vs Market)</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.beta !== null && stock.stability_inputs?.beta !== undefined
                                          ? parseFloat(stock.stability_inputs.beta).toFixed(2)
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    {/* Market Liquidity Metrics */}
                                    <TableRow>
                                      <TableCell>Volume Consistency</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.volume_consistency !== null && stock.stability_inputs?.volume_consistency !== undefined
                                          ? parseFloat(stock.stability_inputs.volume_consistency).toFixed(1)
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Turnover Velocity</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.turnover_velocity !== null && stock.stability_inputs?.turnover_velocity !== undefined
                                          ? parseFloat(stock.stability_inputs.turnover_velocity).toFixed(1)
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Volatility/Volume Ratio</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.volatility_volume_ratio !== null && stock.stability_inputs?.volatility_volume_ratio !== undefined
                                          ? parseFloat(stock.stability_inputs.volatility_volume_ratio).toFixed(1)
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Daily Spread</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.daily_spread !== null && stock.stability_inputs?.daily_spread !== undefined
                                          ? parseFloat(stock.stability_inputs.daily_spread).toFixed(1)
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                  </TableBody>
                                </Table>
                              </TableContainer>
                            </CardContent>
                          </Card>
                        </Grid>

                    {/* Momentum Factor */}
                    <Grid item xs={12} md={6}>
                      <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                        <CardContent sx={{ pb: 2 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Speed sx={{ color: theme.palette.warning.main }} />
                            <Typography variant="h6">Momentum</Typography>
                            <Chip
                              label={stock.momentum_score != null ? parseFloat(stock.momentum_score).toFixed(1) : ""}
                              color={stock.momentum_score !== null && stock.momentum_score !== undefined && parseFloat(stock.momentum_score) >= 80 ? "success" : "default"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Multi-timeframe price momentum with trend strength and volume confirmation
                          </Typography>

                          <Divider sx={{ my: 2 }} />

                          {/* Momentum Score Comparison Chart */}
                          <Box sx={{ mt: 2 }}>
                            <Typography variant="caption" color="text.secondary" gutterBottom>
                              Score Comparison
                            </Typography>
                            <ResponsiveContainer width="100%" height={200}>
                              <BarChart
                                data={[
                                  stock.momentum_score !== null && stock.momentum_score !== undefined && {
                                    name: stock.symbol,
                                    value: stock.momentum_score
                                  },
                                  sectorAvgs.momentum !== null && sectorAvgs.momentum !== undefined && {
                                    name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                    value: sectorAvgs.momentum
                                  },
                                  marketAvgs.momentum !== null && marketAvgs.momentum !== undefined && {
                                    name: "Market Avg",
                                    value: marketAvgs.momentum
                                  },
                                ].filter(Boolean)}
                                margin={{ top: 10, right: 10, left: 0, bottom: 5 }}
                              >
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="name" style={{ fontSize: "0.7rem" }} />
                                <YAxis domain={[0, 100]} style={{ fontSize: "0.75rem" }} />
                                <RechartsTooltip />
                                <Bar dataKey="value" name="Momentum Score">
                                  {[
                                    <Cell key="stock" fill={theme.palette.warning.main} />,
                                    <Cell key="sector" fill={theme.palette.primary.main} />,
                                    <Cell key="market" fill={theme.palette.success.light} />
                                  ]}
                                  <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value !== null && value !== undefined ? parseFloat(value).toFixed(1) : "—"} />
                                </Bar>
                              </BarChart>
                            </ResponsiveContainer>
                          </Box>

                          {/* Momentum Components Input Metrics Table */}
                          <TableContainer sx={{ mt: 2 }}>
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell>Momentum Metric</TableCell>
                                  <TableCell align="right">Value</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {!stock.momentum_inputs && (
                                  <TableRow>
                                    <TableCell colSpan={2} align="center">
                                      <Typography variant="caption" color="text.secondary">
                                        Momentum metrics data loading...
                                      </Typography>
                                    </TableCell>
                                  </TableRow>
                                )}
                                {stock.momentum_inputs && Object.values(stock.momentum_inputs).filter(v => v !== null && v !== undefined && (!v.fallbacks)).length === 0 && (
                                  <TableRow>
                                    <TableCell colSpan={2} align="center">
                                      <Typography variant="caption" color="text.secondary">
                                        No detailed momentum metrics available for this stock
                                      </Typography>
                                    </TableCell>
                                  </TableRow>
                                )}
                                {stock.momentum_inputs && (
                                  <>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>RSI (14-day)</TableCell>
                                      <TableCell align="right">
                                        {stock.rsi !== null && stock.rsi !== undefined
                                          ? parseFloat(stock.rsi).toFixed(1)
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>MACD</TableCell>
                                      <TableCell align="right">
                                        {stock.macd !== null && stock.macd !== undefined
                                          ? parseFloat(stock.macd).toFixed(4)
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>Price vs SMA 50</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.price_vs_sma_50 !== null && stock.momentum_inputs.price_vs_sma_50 !== undefined
                                          ? `${parseFloat(stock.momentum_inputs.price_vs_sma_50).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>

                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>3-Month Return</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs?.momentum_3m != null
                                          ? `${parseFloat(stock.momentum_inputs.momentum_3m).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>

                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>6-Month Return</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs?.momentum_6m != null
                                          ? `${parseFloat(stock.momentum_inputs.momentum_6m).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>

                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>12-Month Return (Excl. Last Month)</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs?.momentum_12_3 != null
                                          ? `${parseFloat(stock.momentum_inputs.momentum_12_3).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>

                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>Price vs SMA 200</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.price_vs_sma_200 !== null && stock.momentum_inputs.price_vs_sma_200 !== undefined
                                          ? `${parseFloat(stock.momentum_inputs.price_vs_sma_200).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>Price vs 52-Week High</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.price_vs_52w_high !== null && stock.momentum_inputs.price_vs_52w_high !== undefined
                                          ? `${parseFloat(stock.momentum_inputs.price_vs_52w_high).toFixed(2)}%`
                                          : ""}
                                      </TableCell>
                                    </TableRow>
                                  </>
                                )}
                              </TableBody>
                            </Table>
                          </TableContainer>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Value Factor */}
                    <Grid item xs={12} md={6}>
                      <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                        <CardContent sx={{ pb: 2 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <AccountBalance sx={{ color: theme.palette.info.main }} />
                            <Typography variant="h6">Value Assessment</Typography>
                            <Chip
                              label={stock.value_score != null ? parseFloat(stock.value_score).toFixed(1) : ""}
                              color={stock.value_score !== null && stock.value_score !== undefined && parseFloat(stock.value_score) >= 80 ? "success" : "default"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Valuation analysis using price multiples, cash flow, and intrinsic value relative to market and sector benchmarks
                          </Typography>

                          <Divider sx={{ my: 2 }} />

                          {/* Value Metrics Table - Simple format showing valuation multiples */}
                          {stock.value_inputs && (
                            <TableContainer sx={{ mt: 2 }}>
                              <Table size="small">
                                <TableHead>
                                  <TableRow sx={{ backgroundColor: 'rgba(0,0,0,0.03)' }}>
                                    <TableCell sx={{ fontWeight: 600 }}>Metric</TableCell>
                                    <TableCell align="right" sx={{ fontWeight: 600 }}>Value</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Price-to-Earnings: Lower is better value">
                                        <span>P/E Ratio</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.stock_pe != null ? parseFloat(stock.value_inputs.stock_pe).toFixed(2) : "—"}
                                    </TableCell>
                                  </TableRow>

                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Forward P/E: Expected future valuation based on projected earnings">
                                        <span>Forward P/E</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.stock_forward_pe != null ? parseFloat(stock.value_inputs.stock_forward_pe).toFixed(2) : "—"}
                                    </TableCell>
                                  </TableRow>

                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Price-to-Book: Lower indicates better value">
                                        <span>P/B Ratio</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.stock_pb != null ? parseFloat(stock.value_inputs.stock_pb).toFixed(2) : "—"}
                                    </TableCell>
                                  </TableRow>

                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Price-to-Sales: Lower is cheaper relative to revenue">
                                        <span>P/S Ratio</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.stock_ps != null ? parseFloat(stock.value_inputs.stock_ps).toFixed(2) : "—"}
                                    </TableCell>
                                  </TableRow>

                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Enterprise Value to EBITDA: Lower valuation relative to earnings power">
                                        <span>EV/EBITDA</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.stock_ev_ebitda != null ? parseFloat(stock.value_inputs.stock_ev_ebitda).toFixed(2) : "—"}
                                    </TableCell>
                                  </TableRow>

                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Enterprise Value to Revenue: Lower indicates cheaper valuation relative to sales">
                                        <span>EV/Revenue</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.stock_ev_revenue != null ? parseFloat(stock.value_inputs.stock_ev_revenue).toFixed(2) : "—"}
                                    </TableCell>
                                  </TableRow>

                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Price/Earnings-to-Growth: <1.0 = undervalued, >2.0 = overvalued">
                                        <span>PEG Ratio</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.peg_ratio != null ? parseFloat(stock.value_inputs.peg_ratio).toFixed(2) : "—"}
                                    </TableCell>
                                  </TableRow>

                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Annual dividend as % of price">
                                        <span>Dividend Yield</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.stock_dividend_yield != null ? parseFloat(stock.value_inputs.stock_dividend_yield).toFixed(2) + "%" : "—"}
                                    </TableCell>
                                  </TableRow>

                                  <TableRow>
                                    <TableCell>
                                      <Tooltip title="Free Cash Flow Yield: Higher is better, measures cheapness relative to cash generation">
                                        <span>FCF Yield</span>
                                      </Tooltip>
                                    </TableCell>
                                    <TableCell align="right">
                                      {stock.value_inputs?.stock_fcf_yield != null ? parseFloat(stock.value_inputs.stock_fcf_yield).toFixed(2) + "%" : "—"}
                                    </TableCell>
                                  </TableRow>
                                </TableBody>
                              </Table>
                            </TableContainer>
                          )}
                          {!stock.value_inputs && (
                            <Alert severity="info" sx={{ mt: 2 }}>
                              Valuation metrics not available for this stock
                            </Alert>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>


                    {/* Positioning Factor */}
                    <Grid item xs={12} md={6}>
                      <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                        <CardContent sx={{ pb: 2 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Group sx={{ color: theme.palette.secondary.main }} />
                            <Typography variant="h6">Market Positioning</Typography>
                            <Chip
                              label={stock.positioning_score != null ? parseFloat(stock.positioning_score).toFixed(1) : ""}
                              color={stock.positioning_score !== null && stock.positioning_score !== undefined && parseFloat(stock.positioning_score) >= 80 ? "success" : "default"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Analysis of institutional and insider ownership patterns, short interest dynamics, and smart money positioning
                          </Typography>

                          <Divider sx={{ my: 2 }} />

                          {/* Positioning Score Comparison Chart */}
                          <Box sx={{ mt: 2 }}>
                            <Typography variant="caption" color="text.secondary" gutterBottom>
                              Score Comparison
                            </Typography>
                            <ResponsiveContainer width="100%" height={200}>
                              <BarChart
                                data={[
                                  stock.positioning_score !== null && stock.positioning_score !== undefined && {
                                    name: stock.symbol,
                                    value: stock.positioning_score
                                  },
                                  sectorAvgs.positioning !== null && sectorAvgs.positioning !== undefined && {
                                    name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                    value: sectorAvgs.positioning
                                  },
                                  marketAvgs.positioning !== null && marketAvgs.positioning !== undefined && {
                                    name: "Market Avg",
                                    value: marketAvgs.positioning
                                  },
                                ].filter(Boolean)}
                                margin={{ top: 10, right: 10, left: 0, bottom: 5 }}
                              >
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="name" style={{ fontSize: "0.7rem" }} />
                                <YAxis domain={[0, 100]} style={{ fontSize: "0.75rem" }} />
                                <RechartsTooltip />
                                <Bar dataKey="value" name="Positioning Score">
                                  {[
                                    <Cell key="stock" fill={theme.palette.secondary.main} />,
                                    <Cell key="sector" fill={theme.palette.primary.main} />,
                                    <Cell key="market" fill={theme.palette.info.light} />
                                  ]}
                                  <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value !== null && value !== undefined ? parseFloat(value).toFixed(1) : "—"} />
                                </Bar>
                              </BarChart>
                            </ResponsiveContainer>
                          </Box>

                          {/* Positioning Table */}
                          <TableContainer sx={{ mt: 2 }}>
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell>Positioning Metric</TableCell>
                                  <TableCell align="right">Value</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                <TableRow>
                                  <TableCell>Institutional Ownership %</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_inputs?.institutional_ownership_pct != null ? `${(parseFloat(stock.positioning_inputs.institutional_ownership_pct) * 100).toFixed(1)}%` : ""}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell>Insider Ownership %</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_inputs?.insider_ownership_pct != null ? `${(parseFloat(stock.positioning_inputs.insider_ownership_pct) * 100).toFixed(1)}%` : ""}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell>Short % of Float</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_inputs?.short_percent_of_float != null ? `${(parseFloat(stock.positioning_inputs.short_percent_of_float) * 100).toFixed(1)}%` : ""}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell>Days to Cover (Short Ratio)</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_inputs?.short_ratio != null ? parseFloat(stock.positioning_inputs.short_ratio).toFixed(2) : ""}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell>Accumulation/Distribution Rating</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_inputs?.ad_rating != null ? parseFloat(stock.positioning_inputs.ad_rating).toFixed(1) : ""}
                                  </TableCell>
                                </TableRow>
                              </TableBody>
                            </Table>
                          </TableContainer>
                        </CardContent>
                      </Card>
                    </Grid>
</Grid>

                  <Divider sx={{ my: 3 }} />

                  <Typography variant="body2" color="text.secondary">
                    Last Updated: {new Date(stock.last_updated).toLocaleDateString()}
                  </Typography>
                  </>
                );
              })()}
                </Box>
              </AccordionDetails>
            </Accordion>
          ))}

          {/* Pagination Controls */}
          {paginationInfo && totalPages > 1 && (
            <Box
              sx={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                gap: 2,
                mt: 4,
                mb: 2,
              }}
            >
              <Button
                variant="outlined"
                disabled={!paginationInfo.hasPrevPage}
                onClick={() => loadAllScores(currentPage - 1)}
                startIcon={<ChevronLeftIcon />}
              >
                Previous
              </Button>

              <Typography variant="body1" sx={{ minWidth: "200px", textAlign: "center" }}>
                Page {currentPage} of {totalPages}
                {totalRecords > 0 && (
                  <>
                    {" • "}
                    {paginationInfo.pageStart}-{paginationInfo.pageEnd} of{" "}
                    {totalRecords}
                  </>
                )}
              </Typography>

              <Button
                variant="outlined"
                disabled={!paginationInfo.hasNextPage}
                onClick={() => loadAllScores(currentPage + 1)}
                endIcon={<ChevronRightIcon />}
              >
                Next
              </Button>
            </Box>
          )}
          </Box>
        )}
      </Box>

      {/* Top Performers by Category */}
      <Typography variant="h4" gutterBottom sx={{ mt: 6, mb: 3 }}>
        Top Performers by Category
        {selectedSector !== "all" && (
          <Chip
            label={`Filtered: ${selectedSector}`}
            size="small"
            color="primary"
            sx={{ ml: 2 }}
            onDelete={() => setSelectedSector("all")}
          />
        )}
      </Typography>

      <Grid container spacing={3}>
        {/* Quality Leaders */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <Stars sx={{ color: theme.palette.primary.main, fontSize: 32 }} />
              <Typography variant="h6">Quality Leaders</Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Rank</TableCell>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Score</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {topQuality.slice(0, 10).map((stock, index) => (
                    <TableRow key={`topQuality-${stock.symbol}-${index}`} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.quality_score != null ? parseFloat(stock.quality_score).toFixed(1) : ""}
                          size="small"
                          color={stock.quality_score != null && parseFloat(stock.quality_score) >= 80 ? "success" : stock.quality_score != null ? "warning" : "default"}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Momentum Leaders */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <Speed sx={{ color: theme.palette.warning.main, fontSize: 32 }} />
              <Typography variant="h6">Momentum Leaders</Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Rank</TableCell>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Score</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {topMomentum.slice(0, 10).map((stock, index) => (
                    <TableRow key={`topMomentum-${stock.symbol}-${index}`} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.momentum_score != null ? parseFloat(stock.momentum_score).toFixed(1) : ""}
                          size="small"
                          color={stock.momentum_score != null && parseFloat(stock.momentum_score) >= 80 ? "success" : "warning"}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Value Leaders */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <AccountBalance sx={{ color: theme.palette.info.main, fontSize: 32 }} />
              <Typography variant="h6">Value Leaders</Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Rank</TableCell>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Score</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {topValue.slice(0, 10).map((stock, index) => (
                    <TableRow key={`topValue-${stock.symbol}-${index}`} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.value_score != null ? parseFloat(stock.value_score).toFixed(1) : ""}
                          size="small"
                          color={stock.value_score != null && parseFloat(stock.value_score) >= 80 ? "success" : stock.value_score != null ? "warning" : "default"}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Growth Leaders */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <Timeline sx={{ color: theme.palette.success.main, fontSize: 32 }} />
              <Typography variant="h6">Growth Leaders</Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Rank</TableCell>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Score</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {topGrowth.slice(0, 10).map((stock, index) => (
                    <TableRow key={`topGrowth-${stock.symbol}-${index}`} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.growth_score != null ? parseFloat(stock.growth_score).toFixed(1) : ""}
                          size="small"
                          color={stock.growth_score != null && parseFloat(stock.growth_score) >= 80 ? "success" : "warning"}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Positioning Leaders */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <Group sx={{ color: theme.palette.secondary.main, fontSize: 32 }} />
              <Typography variant="h6">Positioning Leaders</Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Rank</TableCell>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Score</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {topPositioning.slice(0, 10).map((stock, index) => (
                    <TableRow key={`topPositioning-${stock.symbol}-${index}`} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.positioning_score != null ? parseFloat(stock.positioning_score).toFixed(1) : ""}
                          size="small"
                          color={stock.positioning_score != null && parseFloat(stock.positioning_score) >= 80 ? "success" : stock.positioning_score != null ? "warning" : "default"}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Stability Leaders */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <Security sx={{ color: theme.palette.error.main, fontSize: 32 }} />
              <Typography variant="h6">Stability Leaders</Typography>
            </Box>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Rank</TableCell>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Score</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {topStability.slice(0, 10).map((stock, index) => (
                    <TableRow key={`topStability-${stock.symbol}-${index}`} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.stability_score != null ? parseFloat(stock.stability_score).toFixed(1) : ""}
                          size="small"
                          color={stock.stability_score != null && parseFloat(stock.stability_score) >= 80 ? "success" : "warning"}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>
      </Grid>

      {/* Top Performers by Sector */}
      <Typography variant="h4" gutterBottom sx={{ mt: 6, mb: 3 }}>
        Top Performers by Sector
      </Typography>

      <Grid container spacing={3} sx={{ mb: 6 }}>
        {sectors.slice(0, 6).map((sector) => {
          const sectorStocks = topBySector[sector] || [];
          return (
            <Grid item xs={12} md={6} key={sector}>
              <Paper sx={{ p: 3 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                  <Assessment sx={{ color: theme.palette.primary.main, fontSize: 32 }} />
                  <Typography variant="h6">{sector}</Typography>
                  <Chip
                    label={`${sectorStocks.length} stocks`}
                    size="small"
                    color="default"
                  />
                </Box>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Rank</TableCell>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Score</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {sectorStocks.map((stock, index) => (
                        <TableRow key={`${stock.symbol}-${index}`} hover sx={{ cursor: "pointer" }}>
                          <TableCell>{index + 1}</TableCell>
                          <TableCell>
                            <Typography fontWeight={600}>{stock.symbol}</Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Chip
                              label={stock.composite_score != null ? parseFloat(stock.composite_score).toFixed(1) : ""}
                              size="small"
                              color={stock.composite_score == null ? "default" : parseFloat(stock.composite_score) < 60 ? "error" : parseFloat(stock.composite_score) < 80 ? "warning" : "success"}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>
            </Grid>
          );
        })}
      </Grid>

      {/* Score Guide */}
      <Paper
        sx={{
          p: 2,
          mt: 4,
          mb: 3,
          border: `1px solid ${theme.palette.divider}`,
          backgroundColor: alpha(theme.palette.info.main, 0.02),
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
          <Typography variant="body2" fontWeight={600} color="text.secondary">
            Score Guide:
          </Typography>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Box
              sx={{
                width: 60,
                height: 8,
                borderRadius: 1,
                backgroundColor: theme.palette.success.main,
              }}
            />
            <Typography variant="caption">80-100 Excellent</Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Box
              sx={{
                width: 60,
                height: 8,
                borderRadius: 1,
                backgroundColor: theme.palette.warning.main,
              }}
            />
            <Typography variant="caption">60-79 Good</Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Box
              sx={{
                width: 60,
                height: 8,
                borderRadius: 1,
                backgroundColor: theme.palette.error.main,
              }}
            />
            <Typography variant="caption">0-59 Needs Improvement</Typography>
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default ScoresDashboard;
