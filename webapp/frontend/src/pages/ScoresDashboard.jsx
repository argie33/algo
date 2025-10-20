import { useState, useEffect } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
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
          label: "N/A",
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
  const [loading, setLoading] = useState(true);
  const [scores, setScores] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedStock, setExpandedStock] = useState(null);
  const [signals, setSignals] = useState({});
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [displayLimit, setDisplayLimit] = useState(25);
  const [showAllStocks, setShowAllStocks] = useState(false);

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
  const calculateMarketAverages = (stocks) => {
    if (!stocks || stocks.length === 0) return {};

    const sum = (arr) => arr.reduce((a, b) => a + b, 0);
    const avg = (arr) => arr.length > 0 ? sum(arr) / arr.length : 0;

    return {
      quality: avg(stocks.map(s => s.quality_score || 0).filter(v => v > 0)),
      momentum: avg(stocks.map(s => s.momentum_score || 0).filter(v => v > 0)),
      value: avg(stocks.map(s => s.value_score || 0).filter(v => v > 0)),
      growth: avg(stocks.map(s => s.growth_score || 0).filter(v => v > 0)),
      positioning: avg(stocks.map(s => s.positioning_score || 0).filter(v => v > 0)),
      sentiment: avg(stocks.map(s => s.sentiment_score || 0).filter(v => v > 0)),
      consistency: avg(stocks.map(s => s.stability_score || 0).filter(v => v > 0)),
    };
  };

  // Calculate sector averages for each score category
  const calculateSectorAverages = (stocks, sector) => {
    if (!sector || sector === 'all' || !stocks || stocks.length === 0) return {};

    const sectorStocks = stocks.filter(s => s.sector === sector);
    if (sectorStocks.length === 0) return {};

    const sum = (arr) => arr.reduce((a, b) => a + b, 0);
    const avg = (arr) => arr.length > 0 ? sum(arr) / arr.length : 0;

    return {
      quality: avg(sectorStocks.map(s => s.quality_score || 0).filter(v => v > 0)),
      momentum: avg(sectorStocks.map(s => s.momentum_score || 0).filter(v => v > 0)),
      value: avg(sectorStocks.map(s => s.value_score || 0).filter(v => v > 0)),
      growth: avg(sectorStocks.map(s => s.growth_score || 0).filter(v => v > 0)),
      positioning: avg(sectorStocks.map(s => s.positioning_score || 0).filter(v => v > 0)),
      sentiment: avg(sectorStocks.map(s => s.sentiment_score || 0).filter(v => v > 0)),
      risk: avg(sectorStocks.map(s => s.stability_score || 0).filter(v => v > 0)),
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
      loadSignalsForStocks(scores.slice(0, 20));
    }
  }, [scores]);

  const loadAllScores = async () => {
    setLoading(true);
    try {
      const { default: api } = await import("../services/api");
      const response = await api.get("/api/scores");

      if (response?.data?.success && response.data?.data?.stocks) {
        const transformedStocks = response.data.data.stocks.map(transformStockData);
        setScores(transformedStocks);
      } else {
        console.error("Invalid API response format:", response);
        setScores([]);
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

      const signalPromises = stockList.map(async (stock) => {
        try {
          const response = await api.get(
            `/api/signals?symbol=${stock.symbol}&timeframe=daily&limit=1`
          );
          // Check if we got a valid signal (not "None" or empty)
          if (response?.data?.success && response.data.data?.length > 0) {
            const apiSignal = response.data.data[0].signal;
            // Only use API signal if it's a valid BUY/SELL/HOLD signal
            if (apiSignal && apiSignal.toUpperCase() !== "NONE" &&
                ["BUY", "SELL", "HOLD"].includes(apiSignal.toUpperCase())) {
              return {
                symbol: stock.symbol,
                signal: apiSignal,
                confidence: response.data.data[0].confidence || 0.75,
                date: response.data.data[0].date,
              };
            }
          }
        } catch (err) {
          // API call failed, generate signal from scores
        }

        // Generate signal based on composite score and momentum
        const generateSignal = (stock) => {
          const composite = stock.composite_score;
          const momentum = stock.momentum_score;

          // Strong buy: High composite score (>80) with strong momentum
          if (composite >= 80 && momentum >= 75) {
            return { signal: "BUY", confidence: 0.85 };
          }
          // Buy: Good composite score (>70) with positive momentum
          if (composite >= 70 && momentum >= 65) {
            return { signal: "BUY", confidence: 0.75 };
          }
          // Sell: Low composite score (<50) or weak momentum
          if (composite < 50 || momentum < 40) {
            return { signal: "SELL", confidence: 0.70 };
          }
          // Hold: Everything else
          return { signal: "HOLD", confidence: 0.65 };
        };

        const generated = generateSignal(stock);
        return {
          symbol: stock.symbol,
          signal: generated.signal,
          confidence: generated.confidence,
          date: new Date().toISOString().split('T')[0],
        };
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
  const filteredAndSortedScores = scores
    .filter((stock) => {
      const matchesSearch = stock.symbol.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesComposite = stock.composite_score >= minCompositeScore;
      const matchesMomentum = stock.momentum_score >= minMomentumScore;
      const matchesQuality = stock.quality_score >= minQualityScore;
      const matchesValue = stock.value_score >= minValueScore;
      const matchesGrowth = stock.growth_score >= minGrowthScore;
      const matchesSector = selectedSector === "all" || stock.sector === selectedSector;

      return matchesSearch && matchesComposite && matchesMomentum && matchesQuality && matchesValue && matchesGrowth && matchesSector;
    })
    .sort((a, b) => {
      let comparison = 0;
      const aValue = a[sortBy] || 0;
      const bValue = b[sortBy] || 0;
      comparison = bValue - aValue;
      return sortOrder === "desc" ? comparison : -comparison;
    });

  // Get displayed stocks (paginated)
  const displayedStocks = showAllStocks ? filteredAndSortedScores : filteredAndSortedScores.slice(0, displayLimit);

  // Get top performers for each category with optional sector filtering
  const getTopPerformers = (scoreField, count = 10, sector = null) => {
    const filteredScores = sector && sector !== "all"
      ? scores.filter((stock) => stock.sector === sector)
      : scores;

    return [...filteredScores]
      .sort((a, b) => (b[scoreField] || 0) - (a[scoreField] || 0))
      .slice(0, count);
  };

  // Get top performers by sector
  const getTopPerformersBySector = (count = 5) => {
    const bySector = {};
    sectors.forEach((sector) => {
      bySector[sector] = [...scores]
        .filter((stock) => stock.sector === sector)
        .sort((a, b) => (b.composite_score || 0) - (a.composite_score || 0))
        .slice(0, count);
    });
    return bySector;
  };

  const topQuality = getTopPerformers("quality_score", 10, selectedSector);
  const topMomentum = getTopPerformers("momentum_score", 10, selectedSector);
  const topValue = getTopPerformers("value_score", 10, selectedSector);
  const topGrowth = getTopPerformers("growth_score", 10, selectedSector);
  const topPositioning = getTopPerformers("positioning_score", 10, selectedSector);
  const topSentiment = getTopPerformers("sentiment_score", 10, selectedSector);
  const topBySector = getTopPerformersBySector(5);

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
    const isPositive = change >= 0;
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
          {change.toFixed(2)}%
        </Typography>
      </Box>
    );
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

      {/* Summary Stats */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Paper
            sx={{
              p: 2,
              textAlign: "center",
              background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)}, ${alpha(theme.palette.primary.main, 0.05)})`,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Typography variant="h3" color="primary" fontWeight={700}>
              {scores.length}
            </Typography>
            <Typography variant="body2" color="text.secondary" fontWeight={600}>
              Total Stocks Analyzed
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Paper
            sx={{
              p: 2,
              textAlign: "center",
              background: `linear-gradient(135deg, ${alpha(theme.palette.success.main, 0.1)}, ${alpha(theme.palette.success.main, 0.05)})`,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Typography variant="h3" color="success.main" fontWeight={700}>
              {scores.length > 0
                ? Math.max(...scores.map((s) => s.composite_score)).toFixed(1)
                : 0}
            </Typography>
            <Typography variant="body2" color="text.secondary" fontWeight={600}>
              Highest Overall Score
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Paper
            sx={{
              p: 2,
              textAlign: "center",
              background: `linear-gradient(135deg, ${alpha(theme.palette.info.main, 0.1)}, ${alpha(theme.palette.info.main, 0.05)})`,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Typography variant="h3" color="info.main" fontWeight={700}>
              {scores.length > 0
                ? (
                    scores.reduce((sum, s) => sum + s.composite_score, 0) /
                    scores.length
                  ).toFixed(1)
                : 0}
            </Typography>
            <Typography variant="body2" color="text.secondary" fontWeight={600}>
              Market Average
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Paper
            sx={{
              p: 2,
              textAlign: "center",
              background: `linear-gradient(135deg, ${alpha(theme.palette.warning.main, 0.1)}, ${alpha(theme.palette.warning.main, 0.05)})`,
              border: `1px solid ${theme.palette.divider}`,
            }}
          >
            <Typography variant="h3" color="warning.main" fontWeight={700}>
              {scores.filter((s) => s.composite_score >= 80).length}
            </Typography>
            <Typography variant="body2" color="text.secondary" fontWeight={600}>
              High Quality Stocks (80+)
            </Typography>
          </Paper>
        </Grid>
      </Grid>

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
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
          <Typography variant="h5" gutterBottom>
            Top Overall Stocks ({filteredAndSortedScores.length})
          </Typography>
          {filteredAndSortedScores.length > displayLimit && !showAllStocks && (
            <Button
              variant="outlined"
              size="small"
              onClick={() => setShowAllStocks(true)}
              startIcon={<ExpandMore />}
            >
              Show All {filteredAndSortedScores.length} Stocks
            </Button>
          )}
          {showAllStocks && filteredAndSortedScores.length > displayLimit && (
            <Button
              variant="outlined"
              size="small"
              onClick={() => setShowAllStocks(false)}
              startIcon={<ExpandMore sx={{ transform: "rotate(180deg)" }} />}
            >
              Show Top {displayLimit} Only
            </Button>
          )}
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
            {displayedStocks.map((stock) => (
            <Accordion
              key={stock.symbol}
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
                    <ScoreGauge score={Math.round(stock.composite_score)} size={70} showGrade />
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
                              {(stock.quality_score ?? 0).toFixed(0)}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={stock.quality_score ?? 0}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: (stock.quality_score ?? 0) >= 80
                                  ? theme.palette.success.main
                                  : (stock.quality_score ?? 0) >= 60
                                  ? theme.palette.warning.main
                                  : theme.palette.error.main,
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
                              {(stock.momentum_score ?? 0).toFixed(0)}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={stock.momentum_score ?? 0}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: (stock.momentum_score ?? 0) >= 80
                                  ? theme.palette.success.main
                                  : (stock.momentum_score ?? 0) >= 60
                                  ? theme.palette.warning.main
                                  : theme.palette.error.main,
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
                              {stock.value_score != null ? stock.value_score.toFixed(0) : "N/A"}
                            </Typography>
                          </Box>
                          {stock.value_score != null && (
                            <LinearProgress
                              variant="determinate"
                              value={stock.value_score}
                              sx={{
                                height: 8,
                                borderRadius: 1,
                                backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                                "& .MuiLinearProgress-bar": {
                                  backgroundColor: stock.value_score >= 80
                                    ? theme.palette.success.main
                                    : stock.value_score >= 60
                                    ? theme.palette.warning.main
                                    : theme.palette.error.main,
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
                              {(stock.growth_score ?? 0).toFixed(0)}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={stock.growth_score ?? 0}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: (stock.growth_score ?? 0) >= 80
                                  ? theme.palette.success.main
                                  : (stock.growth_score ?? 0) >= 60
                                  ? theme.palette.warning.main
                                  : theme.palette.error.main,
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
                              {(stock.positioning_score ?? 0).toFixed(0)}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={stock.positioning_score ?? 0}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: (stock.positioning_score ?? 0) >= 80
                                  ? theme.palette.success.main
                                  : (stock.positioning_score ?? 0) >= 60
                                  ? theme.palette.warning.main
                                  : theme.palette.error.main,
                                borderRadius: 1,
                              },
                            }}
                          />
                        </Box>
                      </Grid>

                      {/* Sentiment Score */}
                      <Grid item xs={6} sm={4}>
                        <Box>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                              Sentiment
                            </Typography>
                            <Typography variant="caption" fontWeight={700}>
                              {stock.sentiment_score?.toFixed(0) ?? "N/A"}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={Math.max(0, stock.sentiment_score ?? 0)}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: (stock.sentiment_score ?? 0) >= 80
                                  ? theme.palette.success.main
                                  : (stock.sentiment_score ?? 0) >= 60
                                  ? theme.palette.warning.main
                                  : theme.palette.error.main,
                                borderRadius: 1,
                              },
                            }}
                          />
                        </Box>
                      </Grid>

                      {/* Stability Score */}
                      <Grid item xs={6} sm={4}>
                        <Box>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Typography variant="caption" color="text.secondary" fontWeight={600}>
                              Risk
                            </Typography>
                            <Typography variant="caption" fontWeight={700}>
                              {(stock.stability_score || 0).toFixed(0)}
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={Math.min(100, stock.stability_score || 0)}
                            sx={{
                              height: 8,
                              borderRadius: 1,
                              backgroundColor: alpha(theme.palette.action.disabled, 0.1),
                              "& .MuiLinearProgress-bar": {
                                backgroundColor: (stock.stability_score || 0) < 30
                                  ? theme.palette.success.main
                                  : (stock.stability_score || 0) < 50
                                  ? theme.palette.warning.main
                                  : (stock.stability_score || 0) < 70
                                  ? theme.palette.error.main
                                  : theme.palette.error.main,
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
                                  label={stock.quality_score?.toFixed(1) || "N/A"}
                                  color={stock.quality_score >= 80 ? "success" : "warning"}
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
                                        value: stock.quality_score || 0
                                      },
                                      {
                                        name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                        value: sectorAvgs.quality || 0
                                      },
                                      {
                                        name: "Market Avg",
                                        value: marketAvgs.quality || 0
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
                                      <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value.toFixed(1)} />
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
                                        <TableRow>
                                          <TableCell>Return on Equity (ROE)</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.return_on_equity_pct !== null && stock.quality_inputs.return_on_equity_pct !== undefined
                                              ? `${(stock.quality_inputs.return_on_equity_pct * 100).toFixed(1)}%`
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Return on Assets (ROA)</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.return_on_assets_pct !== null && stock.quality_inputs.return_on_assets_pct !== undefined
                                              ? `${(stock.quality_inputs.return_on_assets_pct * 100).toFixed(1)}%`
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Gross Margin</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.gross_margin_pct !== null && stock.quality_inputs.gross_margin_pct !== undefined
                                              ? `${(stock.quality_inputs.gross_margin_pct * 100).toFixed(1)}%`
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Operating Margin</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.operating_margin_pct !== null && stock.quality_inputs.operating_margin_pct !== undefined
                                              ? `${(stock.quality_inputs.operating_margin_pct * 100).toFixed(1)}%`
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Profit Margin</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.profit_margin_pct !== null && stock.quality_inputs.profit_margin_pct !== undefined
                                              ? `${(stock.quality_inputs.profit_margin_pct * 100).toFixed(1)}%`
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>FCF / Net Income</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.fcf_to_net_income !== null && stock.quality_inputs.fcf_to_net_income !== undefined
                                              ? stock.quality_inputs.fcf_to_net_income.toFixed(2)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Operating CF / Net Income</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.operating_cf_to_net_income !== null && stock.quality_inputs.operating_cf_to_net_income !== undefined
                                              ? stock.quality_inputs.operating_cf_to_net_income.toFixed(2)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Debt-to-Equity Ratio</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.debt_to_equity !== null && stock.quality_inputs.debt_to_equity !== undefined
                                              ? stock.quality_inputs.debt_to_equity.toFixed(2)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Current Ratio</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.current_ratio !== null && stock.quality_inputs.current_ratio !== undefined
                                              ? stock.quality_inputs.current_ratio.toFixed(2)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Quick Ratio</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.quick_ratio !== null && stock.quality_inputs.quick_ratio !== undefined
                                              ? stock.quality_inputs.quick_ratio.toFixed(2)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Earnings Surprise Avg (4Q)</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.earnings_surprise_avg !== null && stock.quality_inputs.earnings_surprise_avg !== undefined
                                              ? `${stock.quality_inputs.earnings_surprise_avg.toFixed(2)}%`
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>EPS Growth Stability (Std Dev)</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.eps_growth_stability !== null && stock.quality_inputs.eps_growth_stability !== undefined
                                              ? stock.quality_inputs.eps_growth_stability.toFixed(2)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                        <TableRow>
                                          <TableCell>Payout Ratio</TableCell>
                                          <TableCell align="right">
                                            {stock.quality_inputs.payout_ratio !== null && stock.quality_inputs.payout_ratio !== undefined
                                              ? `${(stock.quality_inputs.payout_ratio * 100).toFixed(1)}%`
                                              : "N/A"}
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
                                <AccountBalance sx={{ color: theme.palette.success.main }} />
                                <Typography variant="h6">Value Metrics</Typography>
                                <Chip
                                  label={stock.value_score?.toFixed(1) || "N/A"}
                                  color={stock.value_score >= 80 ? "success" : "warning"}
                                  size="small"
                                />
                              </Box>
                              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                                Stock | Sector | Market
                              </Typography>

                              <Divider sx={{ my: 2 }} />

                              <TableContainer>
                                <Table size="small">
                                  <TableHead>
                                    <TableRow>
                                      <TableCell>Metric</TableCell>
                                      <TableCell align="right">Stock</TableCell>
                                      <TableCell align="right">Sector</TableCell>
                                      <TableCell align="right">Market</TableCell>
                                    </TableRow>
                                  </TableHead>
                                  <TableBody>
                                    <TableRow>
                                      <TableCell>P/E Ratio</TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.stock_pe?.toFixed(2) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.sector_pe?.toFixed(2) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.market_pe?.toFixed(2) || "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Price/Book</TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.stock_pb?.toFixed(3) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.sector_pb?.toFixed(3) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.market_pb?.toFixed(3) || "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Price/Sales</TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.stock_ps?.toFixed(3) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.sector_ps?.toFixed(3) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.market_ps?.toFixed(3) || "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>EV/EBITDA</TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.stock_ev_ebitda?.toFixed(2) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.sector_ev_ebitda?.toFixed(2) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">N/A</TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>FCF Yield</TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.stock_fcf_yield?.toFixed(2) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.sector_fcf_yield?.toFixed(2) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.market_fcf_yield?.toFixed(2) || "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Dividend Yield</TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.stock_dividend_yield?.toFixed(3) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.sector_dividend_yield?.toFixed(3) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.market_dividend_yield?.toFixed(3) || "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>PEG Ratio</TableCell>
                                      <TableCell align="right">
                                        {stock.value_inputs?.peg_ratio?.toFixed(2) || "N/A"}
                                      </TableCell>
                                      <TableCell align="right">N/A</TableCell>
                                      <TableCell align="right">N/A</TableCell>
                                    </TableRow>
                                  </TableBody>
                                </Table>
                              </TableContainer>
                            </CardContent>
                          </Card>
                        </Grid>

                        {/* Growth Factor */}
                        <Grid item xs={12} md={6}>
                          <Card>
                            <CardContent>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                                <TrendingUp sx={{ color: theme.palette.info.main }} />
                                <Typography variant="h6">Growth Metrics</Typography>
                                <Chip
                                  label={stock.growth_score?.toFixed(1) || "N/A"}
                                  color={stock.growth_score >= 80 ? "success" : "warning"}
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
                                        {stock.growth_inputs?.revenue_growth_3y_cagr != null ? `${stock.growth_inputs.revenue_growth_3y_cagr.toFixed(2)}%` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>EPS CAGR (3Y)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.eps_growth_3y_cagr != null ? `${stock.growth_inputs.eps_growth_3y_cagr.toFixed(2)}%` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Net Income Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.net_income_growth_yoy != null ? `${stock.growth_inputs.net_income_growth_yoy.toFixed(2)}%` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Op Income Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.operating_income_growth_yoy != null ? `${stock.growth_inputs.operating_income_growth_yoy.toFixed(2)}%` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Gross Margin Trend</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.gross_margin_trend != null ? `${stock.growth_inputs.gross_margin_trend.toFixed(2)} pp` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Operating Margin Trend</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.operating_margin_trend != null ? `${stock.growth_inputs.operating_margin_trend.toFixed(2)} pp` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Net Margin Trend</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.net_margin_trend != null ? `${stock.growth_inputs.net_margin_trend.toFixed(2)} pp` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>ROE Trend</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.roe_trend != null ? `${stock.growth_inputs.roe_trend.toFixed(2)}` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Sustainable Growth Rate</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.sustainable_growth_rate != null ? `${stock.growth_inputs.sustainable_growth_rate.toFixed(2)}%` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Quarterly Growth Momentum</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.quarterly_growth_momentum != null ? `${stock.growth_inputs.quarterly_growth_momentum.toFixed(2)} pp` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>FCF Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.fcf_growth_yoy != null ? `${stock.growth_inputs.fcf_growth_yoy.toFixed(2)}%` : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Asset Growth (YoY)</TableCell>
                                      <TableCell align="right">
                                        {stock.growth_inputs?.asset_growth_yoy != null ? `${stock.growth_inputs.asset_growth_yoy.toFixed(2)}%` : "N/A"}
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
                                  label={(stock.stability_score || 0).toFixed(1)}
                                  color={(stock.stability_score || 0) < 30 ? "success" : (stock.stability_score || 0) < 50 ? "warning" : "error"}
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
                                        value: stock.stability_score || 0
                                      },
                                      {
                                        name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                        value: sectorAvgs.stability || 0
                                      },
                                      {
                                        name: "Market Avg",
                                        value: marketAvgs.stability || 0
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
                                        <Cell key="stock" fill={(stock.stability_score || 0) < 30 ? theme.palette.success.main : (stock.stability_score || 0) < 50 ? theme.palette.warning.main : theme.palette.error.main} />,
                                        <Cell key="sector" fill={theme.palette.primary.main} />,
                                        <Cell key="market" fill={theme.palette.info.light} />
                                      ]}
                                      <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value.toFixed(1)} />
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
                                        {stock.stability_inputs?.volatility_12m_pct !== null && stock.stability_inputs?.volatility_12m_pct !== undefined
                                          ? `${(stock.stability_inputs.volatility_12m_pct || 0).toFixed(2)}%`
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Downside Volatility</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.downside_volatility_pct !== null && stock.stability_inputs?.downside_volatility_pct !== undefined
                                          ? `${(stock.stability_inputs.downside_volatility_pct || 0).toFixed(2)}%`
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Max Drawdown (52W)</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.max_drawdown_52w_pct !== null && stock.stability_inputs?.max_drawdown_52w_pct !== undefined
                                          ? `${(stock.stability_inputs.max_drawdown_52w_pct || 0).toFixed(2)}%`
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Beta (vs Market)</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.beta !== null && stock.stability_inputs?.beta !== undefined
                                          ? (stock.stability_inputs.beta || 0).toFixed(2)
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell>Liquidity Stability Score</TableCell>
                                      <TableCell align="right">
                                        {stock.stability_inputs?.liquidity_risk !== null && stock.stability_inputs?.liquidity_risk !== undefined
                                          ? (stock.stability_inputs.liquidity_risk || 0).toFixed(1)
                                          : "N/A"}
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
                              label={stock.momentum_score?.toFixed(1) || "N/A"}
                              color={stock.momentum_score >= 80 ? "success" : "warning"}
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
                                  {
                                    name: stock.symbol,
                                    value: stock.momentum_score || 0
                                  },
                                  {
                                    name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                    value: sectorAvgs.momentum || 0
                                  },
                                  {
                                    name: "Market Avg",
                                    value: marketAvgs.momentum || 0
                                  },
                                ]}
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
                                  <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value.toFixed(1)} />
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
                                      <TableCell sx={{ fontWeight: 600 }}>Intraweek Trend Confirmation (10pts)</TableCell>
                                      <TableCell align="right"></TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>RSI (14-day)</TableCell>
                                      <TableCell align="right">
                                        {stock.rsi !== null && stock.rsi !== undefined
                                          ? stock.rsi.toFixed(1)
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>MACD</TableCell>
                                      <TableCell align="right">
                                        {stock.macd !== null && stock.macd !== undefined
                                          ? stock.macd.toFixed(4)
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>Price vs SMA 50</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.price_vs_sma_50 !== null && stock.momentum_inputs.price_vs_sma_50 !== undefined
                                          ? `${stock.momentum_inputs.price_vs_sma_50.toFixed(2)}%`
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>

                                    <TableRow>
                                      <TableCell sx={{ fontWeight: 600, pt: 2 }}>Short-Term Momentum (25pts)</TableCell>
                                      <TableCell align="right"></TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>3-Month Return</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.momentum_3m !== null && stock.momentum_inputs.momentum_3m !== undefined
                                          ? `${stock.momentum_inputs.momentum_3m.toFixed(2)}%`
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>

                                    <TableRow>
                                      <TableCell sx={{ fontWeight: 600, pt: 2 }}>Medium-Term Momentum (25pts)</TableCell>
                                      <TableCell align="right"></TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>6-Month Return</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.momentum_6m !== null && stock.momentum_inputs.momentum_6m !== undefined
                                          ? `${stock.momentum_inputs.momentum_6m.toFixed(2)}%`
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>

                                    <TableRow>
                                      <TableCell sx={{ fontWeight: 600, pt: 2 }}>Long-Term Momentum (15pts)</TableCell>
                                      <TableCell align="right"></TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>12-Month Return (Excl. Last Month)</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.momentum_12m_1 !== null && stock.momentum_inputs.momentum_12m_1 !== undefined
                                          ? `${stock.momentum_inputs.momentum_12m_1.toFixed(2)}%`
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>

                                    <TableRow>
                                      <TableCell sx={{ fontWeight: 600, pt: 2 }}>Stability (10pts)</TableCell>
                                      <TableCell align="right"></TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>Price vs SMA 200</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.price_vs_sma_200 !== null && stock.momentum_inputs.price_vs_sma_200 !== undefined
                                          ? `${stock.momentum_inputs.price_vs_sma_200.toFixed(2)}%`
                                          : "N/A"}
                                      </TableCell>
                                    </TableRow>
                                    <TableRow>
                                      <TableCell sx={{ pl: 4 }}>Price vs 52-Week High</TableCell>
                                      <TableCell align="right">
                                        {stock.momentum_inputs.price_vs_52w_high !== null && stock.momentum_inputs.price_vs_52w_high !== undefined
                                          ? `${stock.momentum_inputs.price_vs_52w_high.toFixed(2)}%`
                                          : "N/A"}
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
                              label={stock.value_score?.toFixed(1) || "N/A"}
                              color={stock.value_score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Valuation analysis using price multiples, cash flow, and intrinsic value relative to market and sector benchmarks
                          </Typography>

                          <Divider sx={{ my: 2 }} />

                          {/* Value Score Comparison Chart */}
                          <Box sx={{ mt: 2 }}>
                            <Typography variant="caption" color="text.secondary" gutterBottom>
                              Score Comparison
                            </Typography>
                            <ResponsiveContainer width="100%" height={200}>
                              <BarChart
                                data={[
                                  {
                                    name: stock.symbol,
                                    value: stock.value_score || 0
                                  },
                                  {
                                    name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                    value: sectorAvgs.value || 0
                                  },
                                  {
                                    name: "Market Avg",
                                    value: marketAvgs.value || 0
                                  },
                                ]}
                                margin={{ top: 10, right: 10, left: 0, bottom: 5 }}
                              >
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="name" style={{ fontSize: "0.7rem" }} />
                                <YAxis domain={[0, 100]} style={{ fontSize: "0.75rem" }} />
                                <RechartsTooltip />
                                <Bar dataKey="value" name="Value Score">
                                  {[
                                    <Cell key="stock" fill={theme.palette.info.main} />,
                                    <Cell key="sector" fill={theme.palette.primary.main} />,
                                    <Cell key="market" fill={theme.palette.success.light} />
                                  ]}
                                  <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value.toFixed(1)} />
                                </Bar>
                              </BarChart>
                            </ResponsiveContainer>
                          </Box>

                          {/* Valuation Metrics Table */}
                          {stock.value_inputs && (
                            <TableContainer sx={{ mt: 2 }}>
                              <Table size="small">
                                <TableHead>
                                  <TableRow>
                                    <TableCell>Metric</TableCell>
                                    <TableCell align="right">Value</TableCell>
                                  </TableRow>
                                </TableHead>
                                <TableBody>
                                  <TableRow>
                                    <TableCell>P/E Ratio (Price-to-Earnings)</TableCell>
                                    <TableCell align="right">{stock.value_inputs.stock_pe?.toFixed(2) || "N/A"}</TableCell>
                                  </TableRow>
                                  <TableRow>
                                    <TableCell>P/B Ratio (Price-to-Book)</TableCell>
                                    <TableCell align="right">{stock.value_inputs.stock_pb?.toFixed(2) || "N/A"}</TableCell>
                                  </TableRow>
                                  <TableRow>
                                    <TableCell>P/S Ratio (Price-to-Sales)</TableCell>
                                    <TableCell align="right">{stock.value_inputs.stock_ps?.toFixed(2) || "N/A"}</TableCell>
                                  </TableRow>
                                  <TableRow>
                                    <TableCell>EV/EBITDA</TableCell>
                                    <TableCell align="right">{stock.value_inputs.stock_ev_ebitda?.toFixed(2) || "N/A"}</TableCell>
                                  </TableRow>
                                  <TableRow>
                                    <TableCell>Dividend Yield</TableCell>
                                    <TableCell align="right">{stock.value_inputs.stock_dividend_yield?.toFixed(2) || "N/A"}%</TableCell>
                                  </TableRow>
                                  <TableRow>
                                    <TableCell>FCF Yield (Free Cash Flow Yield)</TableCell>
                                    <TableCell align="right">{stock.value_inputs.stock_fcf_yield?.toFixed(2) || "N/A"}%</TableCell>
                                  </TableRow>
                                  {stock.value_inputs.peg_ratio !== null && stock.value_inputs.peg_ratio !== undefined && (
                                    <TableRow>
                                      <TableCell>PEG Ratio (P/E to Growth)</TableCell>
                                      <TableCell align="right">{stock.value_inputs.peg_ratio.toFixed(2)}</TableCell>
                                    </TableRow>
                                  )}
                                </TableBody>
                              </Table>
                            </TableContainer>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Growth Factor */}
                    <Grid item xs={12} md={6}>
                      <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                        <CardContent sx={{ pb: 2 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Timeline sx={{ color: theme.palette.success.main }} />
                            <Typography variant="h6">Growth Potential</Typography>
                            <Chip
                              label={stock.growth_score?.toFixed(1) || "N/A"}
                              color={stock.growth_score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Revenue and earnings growth trajectory with historical price performance
                          </Typography>

                          <Divider sx={{ my: 2 }} />

                          {/* Growth Score Comparison Chart */}
                          <Box sx={{ mt: 2 }}>
                            <Typography variant="caption" color="text.secondary" gutterBottom>
                              Score Comparison
                            </Typography>
                            <ResponsiveContainer width="100%" height={200}>
                              <BarChart
                                data={[
                                  {
                                    name: stock.symbol,
                                    value: stock.growth_score || 0
                                  },
                                  {
                                    name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                    value: sectorAvgs.growth || 0
                                  },
                                  {
                                    name: "Market Avg",
                                    value: marketAvgs.growth || 0
                                  },
                                ]}
                                margin={{ top: 10, right: 10, left: 0, bottom: 5 }}
                              >
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="name" style={{ fontSize: "0.7rem" }} />
                                <YAxis domain={[0, 100]} style={{ fontSize: "0.75rem" }} />
                                <RechartsTooltip />
                                <Bar dataKey="value" name="Growth Score">
                                  {[
                                    <Cell key="stock" fill={theme.palette.success.main} />,
                                    <Cell key="sector" fill={theme.palette.primary.main} />,
                                    <Cell key="market" fill={theme.palette.info.light} />
                                  ]}
                                  <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value.toFixed(1)} />
                                </Bar>
                              </BarChart>
                            </ResponsiveContainer>
                          </Box>

                          {/* Growth Metrics Table */}
                          <TableContainer sx={{ mt: 2 }}>
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell>Metric</TableCell>
                                  <TableCell align="right">Value</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {!stock.growth_inputs && (
                                  <TableRow>
                                    <TableCell colSpan={2} align="center">
                                      <Typography variant="caption" color="text.secondary">
                                        Growth metrics data loading...
                                      </Typography>
                                    </TableCell>
                                  </TableRow>
                                )}
                                {stock.growth_inputs && Object.values(stock.growth_inputs).every(v => v === null || v === undefined) && (
                                  <TableRow>
                                    <TableCell colSpan={2} align="center">
                                      <Typography variant="caption" color="text.secondary">
                                        No detailed growth metrics available for this stock
                                      </Typography>
                                    </TableCell>
                                  </TableRow>
                                )}
                                {stock.growth_inputs && (
                                  <>
                                    {stock.growth_inputs.revenue_growth_3y_cagr !== null && stock.growth_inputs.revenue_growth_3y_cagr !== undefined && (
                                      <TableRow>
                                        <TableCell>Revenue Growth (3Y CAGR)</TableCell>
                                        <TableCell align="right">{stock.growth_inputs.revenue_growth_3y_cagr.toFixed(1)}%</TableCell>
                                      </TableRow>
                                    )}
                                    {stock.growth_inputs.eps_growth_3y_cagr !== null && stock.growth_inputs.eps_growth_3y_cagr !== undefined && (
                                      <TableRow>
                                        <TableCell>EPS Growth (3Y CAGR)</TableCell>
                                        <TableCell align="right">{stock.growth_inputs.eps_growth_3y_cagr.toFixed(1)}%</TableCell>
                                      </TableRow>
                                    )}
                                    {stock.growth_inputs.operating_income_growth_yoy !== null && stock.growth_inputs.operating_income_growth_yoy !== undefined && (
                                      <TableRow>
                                        <TableCell>Operating Income Growth (YoY)</TableCell>
                                        <TableCell align="right">{stock.growth_inputs.operating_income_growth_yoy.toFixed(1)}%</TableCell>
                                      </TableRow>
                                    )}
                                    {stock.growth_inputs.roe_trend !== null && stock.growth_inputs.roe_trend !== undefined && (
                                      <TableRow>
                                        <TableCell>ROE Trend (YoY Change)</TableCell>
                                        <TableCell align="right">{stock.growth_inputs.roe_trend.toFixed(1)}%</TableCell>
                                      </TableRow>
                                    )}
                                    {stock.growth_inputs.sustainable_growth_rate !== null && stock.growth_inputs.sustainable_growth_rate !== undefined && (
                                      <TableRow>
                                        <TableCell>Sustainable Growth Rate</TableCell>
                                        <TableCell align="right">{stock.growth_inputs.sustainable_growth_rate.toFixed(1)}%</TableCell>
                                      </TableRow>
                                    )}
                                    {stock.growth_inputs.fcf_growth_yoy !== null && stock.growth_inputs.fcf_growth_yoy !== undefined && (
                                      <TableRow>
                                        <TableCell>FCF Growth (YoY)</TableCell>
                                        <TableCell align="right">{stock.growth_inputs.fcf_growth_yoy.toFixed(1)}%</TableCell>
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

                    {/* Positioning Factor */}
                    <Grid item xs={12} md={6}>
                      <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                        <CardContent sx={{ pb: 2 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Group sx={{ color: theme.palette.secondary.main }} />
                            <Typography variant="h6">Market Positioning</Typography>
                            <Chip
                              label={stock.positioning_score?.toFixed(1) || "N/A"}
                              color={stock.positioning_score >= 80 ? "success" : "warning"}
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
                                  {
                                    name: stock.symbol,
                                    value: stock.positioning_score || 0
                                  },
                                  {
                                    name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                    value: sectorAvgs.positioning || 0
                                  },
                                  {
                                    name: "Market Avg",
                                    value: marketAvgs.positioning || 0
                                  },
                                ]}
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
                                  <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value.toFixed(1)} />
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
                                    {stock.positioning_components?.institutional_ownership ? `${(stock.positioning_components.institutional_ownership * 100).toFixed(1)}%` : "N/A"}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell>Insider Ownership %</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_components?.insider_ownership ? `${(stock.positioning_components.insider_ownership * 100).toFixed(1)}%` : "N/A"}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell>Short % of Float</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_components?.short_percent_of_float ? `${(stock.positioning_components.short_percent_of_float * 100).toFixed(1)}%` : "N/A"}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell>Days to Cover (Short Ratio)</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_components?.days_to_cover?.toFixed(2) || stock.positioning_components?.short_ratio?.toFixed(2) || "N/A"}
                                  </TableCell>
                                </TableRow>
                                <TableRow>
                                  <TableCell>Accumulation/Distribution Rating</TableCell>
                                  <TableCell align="right">
                                    {stock.positioning_components?.acc_dist_rating?.toFixed(1) || "N/A"}
                                  </TableCell>
                                </TableRow>
                              </TableBody>
                            </Table>
                          </TableContainer>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Sentiment Factor */}
                    <Grid item xs={12} md={6}>
                      <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
                        <CardContent sx={{ pb: 2 }}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <SentimentSatisfied sx={{ color: theme.palette.success.main }} />
                            <Typography variant="h6">Market Sentiment</Typography>
                            <Chip
                              label={stock.sentiment_score?.toFixed(1) ?? "N/A"}
                              color={(stock.sentiment_score ?? 0) >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                            Market sentiment analysis from news sources, social media, and analyst ratings
                          </Typography>

                          <Divider sx={{ my: 2 }} />

                          {/* Sentiment Score Comparison Chart */}
                          <Box sx={{ mt: 2 }}>
                            <Typography variant="caption" color="text.secondary" gutterBottom>
                              Score Comparison
                            </Typography>
                            <ResponsiveContainer width="100%" height={200}>
                              <BarChart
                                data={[
                                  {
                                    name: stock.symbol,
                                    value: stock.sentiment_score || 0
                                  },
                                  {
                                    name: stock.sector ? `${stock.sector} Avg` : "Sector Avg",
                                    value: sectorAvgs.sentiment || 0
                                  },
                                  {
                                    name: "Market Avg",
                                    value: marketAvgs.sentiment || 0
                                  },
                                ]}
                                margin={{ top: 10, right: 10, left: 0, bottom: 5 }}
                              >
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="name" style={{ fontSize: "0.7rem" }} />
                                <YAxis domain={[0, 100]} style={{ fontSize: "0.75rem" }} />
                                <RechartsTooltip />
                                <Bar dataKey="value" name="Sentiment Score">
                                  {[
                                    <Cell key="stock" fill={theme.palette.success.main} />,
                                    <Cell key="sector" fill={theme.palette.primary.main} />,
                                    <Cell key="market" fill={theme.palette.warning.light} />
                                  ]}
                                  <LabelList dataKey="value" position="top" style={{ fontSize: '0.75rem', fontWeight: 600 }} formatter={(value) => value.toFixed(1)} />
                                </Bar>
                              </BarChart>
                            </ResponsiveContainer>
                          </Box>

                          {/* Sentiment Inputs Table */}
                          <TableContainer sx={{ mt: 2 }}>
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell>Metric</TableCell>
                                  <TableCell align="right">Value</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                <TableRow>
                                  <TableCell colSpan={2} align="center">
                                    <Typography variant="caption" color="text.secondary">
                                      Detailed sentiment metrics coming soon
                                    </Typography>
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
          </Box>
        )}
      </Box>

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
                        <TableRow key={stock.symbol} hover sx={{ cursor: "pointer" }}>
                          <TableCell>{index + 1}</TableCell>
                          <TableCell>
                            <Typography fontWeight={600}>{stock.symbol}</Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Chip
                              label={stock.composite_score.toFixed(1)}
                              size="small"
                              color={stock.composite_score >= 80 ? "success" : stock.composite_score >= 60 ? "warning" : "error"}
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
                    <TableRow key={stock.symbol} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.quality_score.toFixed(1)}
                          size="small"
                          color={stock.quality_score >= 80 ? "success" : "warning"}
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
                    <TableRow key={stock.symbol} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.momentum_score.toFixed(1)}
                          size="small"
                          color={stock.momentum_score >= 80 ? "success" : "warning"}
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
                    <TableRow key={stock.symbol} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.value_score != null ? stock.value_score.toFixed(1) : "N/A"}
                          size="small"
                          color={stock.value_score != null && stock.value_score >= 80 ? "success" : "warning"}
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
                    <TableRow key={stock.symbol} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.growth_score.toFixed(1)}
                          size="small"
                          color={stock.growth_score >= 80 ? "success" : "warning"}
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
                    <TableRow key={stock.symbol} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.positioning_score.toFixed(1)}
                          size="small"
                          color={stock.positioning_score >= 80 ? "success" : "warning"}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        {/* Sentiment Leaders */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <SentimentSatisfied sx={{ color: theme.palette.success.main, fontSize: 32 }} />
              <Typography variant="h6">Sentiment Leaders</Typography>
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
                  {topSentiment.slice(0, 10).map((stock, index) => (
                    <TableRow key={stock.symbol} hover sx={{ cursor: "pointer" }}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell>
                        <Typography fontWeight={600}>{stock.symbol}</Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={stock.sentiment_score?.toFixed(1) ?? "N/A"}
                          size="small"
                          color={(stock.sentiment_score ?? 0) >= 80 ? "success" : "warning"}
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
