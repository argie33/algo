import { useState, useEffect } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
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
  TextField,
  Typography,
  alpha,
  useTheme,
  Tooltip,
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
} from "@mui/icons-material";

// Trading Signal Component
const TradingSignal = ({ signal, confidence = 0.75, size = "medium", showConfidence = false }) => {
  const theme = useTheme();

  const getSignalConfig = (signalType) => {
    switch (signalType?.toUpperCase()) {
      case 'BUY':
        return {
          color: theme.palette.success.main,
          bgColor: alpha(theme.palette.success.main, 0.1),
          icon: <TrendingUp sx={{ fontSize: size === 'small' ? 16 : 20 }} />,
          label: 'BUY',
          textColor: theme.palette.success.dark
        };
      case 'SELL':
        return {
          color: theme.palette.error.main,
          bgColor: alpha(theme.palette.error.main, 0.1),
          icon: <TrendingDown sx={{ fontSize: size === 'small' ? 16 : 20 }} />,
          label: 'SELL',
          textColor: theme.palette.error.dark
        };
      case 'HOLD':
        return {
          color: theme.palette.warning.main,
          bgColor: alpha(theme.palette.warning.main, 0.1),
          icon: <ShowChart sx={{ fontSize: size === 'small' ? 16 : 20 }} />,
          label: 'HOLD',
          textColor: theme.palette.warning.dark
        };
      default:
        return {
          color: theme.palette.grey[500],
          bgColor: alpha(theme.palette.grey[500], 0.1),
          icon: <SignalCellularAlt sx={{ fontSize: size === 'small' ? 16 : 20 }} />,
          label: 'N/A',
          textColor: theme.palette.grey[600]
        };
    }
  };

  const config = getSignalConfig(signal);
  const confidencePercent = Math.round(confidence * 100);

  return (
    <Tooltip title={showConfidence ? `Signal: ${config.label} (${confidencePercent}% confidence)` : `Trading Signal: ${config.label}`}>
      <Box
        sx={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 0.5,
          px: size === 'small' ? 1 : 1.5,
          py: size === 'small' ? 0.25 : 0.5,
          borderRadius: 2,
          backgroundColor: config.bgColor,
          border: `1px solid ${alpha(config.color, 0.3)}`,
          minWidth: size === 'small' ? 60 : 80,
          justifyContent: 'center',
          cursor: 'pointer',
          transition: 'all 0.2s ease-in-out',
          '&:hover': {
            backgroundColor: alpha(config.color, 0.15),
            borderColor: alpha(config.color, 0.5),
            transform: 'translateY(-1px)',
          },
        }}
      >
        {config.icon}
        <Typography
          variant={size === 'small' ? 'caption' : 'body2'}
          sx={{
            color: config.textColor,
            fontWeight: 600,
            fontSize: size === 'small' ? '0.65rem' : '0.75rem',
          }}
        >
          {config.label}
        </Typography>
        {showConfidence && (
          <Typography
            variant="caption"
            sx={{
              color: alpha(config.textColor, 0.7),
              fontSize: '0.6rem',
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

// Custom styled components
const ScoreGauge = ({ score, size = 80, showGrade = false }) => {
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
          <Typography variant="h6" fontWeight={700}>
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
  const [sortBy, setSortBy] = useState("score");
  const [sortOrder, setSortOrder] = useState("desc");

  // Transform data to handle both old and new API formats
  const transformStockData = (stock) => {
    // If already in new format (snake_case), return as is
    if (stock.composite_score !== undefined) {
      return {
        ...stock,
        growth_score: stock.growth_score || 75.0 // Default if missing
      };
    }

    // Transform old format (camelCase + nested factors) to new format
    return {
      symbol: stock.symbol,
      composite_score: stock.compositeScore || 0,
      momentum_score: stock.factors?.momentum?.score || 0,
      trend_score: stock.factors?.trend?.score || 0,
      value_score: stock.factors?.value?.score || 0,
      quality_score: stock.factors?.quality?.score || 0,
      growth_score: 75.0, // Default value
      current_price: stock.currentPrice || 0,
      price_change_1d: stock.priceChange1d || 0,
      price_change_5d: stock.factors?.technical?.priceChange5d || 0,
      price_change_30d: stock.factors?.technical?.priceChange30d || 0,
      volatility_30d: stock.factors?.quality?.volatility || stock.factors?.risk?.volatility30d || 0,
      market_cap: stock.marketCap || 0,
      volume_avg_30d: stock.volume || 0,
      pe_ratio: stock.factors?.value?.peRatio || null,
      rsi: stock.factors?.momentum?.rsi || 0,
      sma_20: stock.factors?.trend?.sma20 || 0,
      sma_50: stock.factors?.trend?.sma50 || 0,
      macd: stock.factors?.technical?.macd || null,
      last_updated: stock.lastUpdated,
      score_date: stock.scoreDate
    };
  };

  // Load all scores on component mount
  useEffect(() => {
    loadAllScores();
  }, []);

  // Load signals for visible stocks
  useEffect(() => {
    if (scores.length > 0) {
      loadSignalsForStocks(scores.slice(0, 20)); // Load signals for first 20 stocks
    }
  }, [scores]);

  const loadAllScores = async () => {
    setLoading(true);
    try {
      // Import the API function
      const { default: api } = await import("../services/api");

      // Fetch all scores data from backend (no limit - filtering done on frontend)
      const response = await api.get("/api/scores");

      if (response?.data?.success && response.data.data?.stocks) {
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

  // Load trading signals for multiple stocks
  const loadSignalsForStocks = async (stockList) => {
    if (signalsLoading || stockList.length === 0) return;

    setSignalsLoading(true);
    try {
      const { default: api } = await import("../services/api");

      // Get latest signals for each stock symbol
      const signalPromises = stockList.map(async (stock) => {
        try {
          const response = await api.get(`/api/signals?symbol=${stock.symbol}&timeframe=daily&limit=1`);
          if (response?.data?.success && response.data.data?.length > 0) {
            return {
              symbol: stock.symbol,
              signal: response.data.data[0].signal,
              confidence: response.data.data[0].confidence || 0.75,
              date: response.data.data[0].date
            };
          }
        } catch (err) {
          console.log(`No signal data for ${stock.symbol}`);
        }
        return null;
      });

      const signalResults = await Promise.all(signalPromises);
      const signalsMap = {};

      signalResults.forEach(result => {
        if (result) {
          signalsMap[result.symbol] = result;
        }
      });

      setSignals(prev => ({ ...prev, ...signalsMap }));
    } catch (error) {
      console.error("Error loading signals:", error);
    } finally {
      setSignalsLoading(false);
    }
  };

  // Filter and sort scores based on search term and sort options
  const filteredAndSortedScores = scores
    .filter((stock) => {
      // Search term filter
      return stock.symbol.toLowerCase().includes(searchTerm.toLowerCase());
    })
    .sort((a, b) => {
      let comparison = 0;

      switch (sortBy) {
        case "score":
          comparison = b.composite_score - a.composite_score;
          break;
        case "symbol":
          comparison = a.symbol.localeCompare(b.symbol);
          break;
        case "price":
          comparison = b.current_price - a.current_price;
          break;
        case "signal": {
          const aSignal = signals[a.symbol]?.signal || "None";
          const bSignal = signals[b.symbol]?.signal || "None";
          comparison = aSignal.localeCompare(bSignal);
          break;
        }
        case "confidence": {
          const aConfidence = signals[a.symbol]?.confidence || 0;
          const bConfidence = signals[b.symbol]?.confidence || 0;
          comparison = bConfidence - aConfidence;
          break;
        }
        default:
          comparison = b.composite_score - a.composite_score;
      }

      return sortOrder === "desc" ? comparison : -comparison;
    });

  const handleAccordionChange = (symbol) => (event, isExpanded) => {
    setExpandedStock(isExpanded ? symbol : null);
  };

  const formatNumber = (num) => {
    if (num >= 1e12) return `$${(num / 1e12).toFixed(1)}T`;
    if (num >= 1e9) return `$${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `$${(num / 1e6).toFixed(1)}M`;
    return `$${num}`;
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
      <Box sx={{ textAlign: "center", mb: 4 }}>
        <Box
          sx={{
            background: `linear-gradient(135deg, ${theme.palette.primary.main}20, ${theme.palette.secondary.main}20)`,
            borderRadius: 2,
            p: 3,
            mb: 3,
          }}
        >
          <Typography variant="h3" component="h1" gutterBottom>
            Stock Scores Dashboard
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Comprehensive six-factor scoring system for all stocks
          </Typography>
        </Box>
      </Box>

      {/* Search and Filter Controls */}
      <Box sx={{ mb: 3, display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
        <TextField
          variant="outlined"
          placeholder="Search stocks by symbol..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          sx={{ minWidth: 250 }}
        />


        <FormControl variant="outlined" sx={{ minWidth: 120 }}>
          <InputLabel>Sort By</InputLabel>
          <Select
            value={sortBy}
            label="Sort By"
            onChange={(e) => setSortBy(e.target.value)}
          >
            <MenuItem value="score">Score</MenuItem>
            <MenuItem value="symbol">Symbol</MenuItem>
            <MenuItem value="price">Price</MenuItem>
            <MenuItem value="signal">Signal</MenuItem>
            <MenuItem value="confidence">Confidence</MenuItem>
          </Select>
        </FormControl>

        <FormControl variant="outlined" sx={{ minWidth: 100 }}>
          <InputLabel>Order</InputLabel>
          <Select
            value={sortOrder}
            label="Order"
            onChange={(e) => setSortOrder(e.target.value)}
          >
            <MenuItem value="desc">High to Low</MenuItem>
            <MenuItem value="asc">Low to High</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {/* Summary Stats */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="h4" color="primary" fontWeight={700}>
              {filteredAndSortedScores.length}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Total Stocks
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="h4" color="success.main" fontWeight={700}>
              {filteredAndSortedScores.length > 0 ? Math.max(...filteredAndSortedScores.map(s => s.composite_score)).toFixed(1) : 0}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Top Score
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="h4" color="info.main" fontWeight={700}>
              {filteredAndSortedScores.length > 0 ? (filteredAndSortedScores.reduce((sum, s) => sum + s.composite_score, 0) / filteredAndSortedScores.length).toFixed(1) : 0}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Average Score
            </Typography>
          </Paper>
        </Grid>
        <Grid item xs={12} md={3}>
          <Paper sx={{ p: 2, textAlign: "center" }}>
            <Typography variant="h4" color="warning.main" fontWeight={700}>
              {filteredAndSortedScores.filter(s => s.composite_score >= 80).length}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              High Quality (80+)
            </Typography>
          </Paper>
        </Grid>
      </Grid>

      {/* Stocks List */}
      <Typography variant="h5" gutterBottom sx={{ mb: 2 }}>
        All Stocks ({filteredAndSortedScores.length})
      </Typography>

      {filteredAndSortedScores.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: "center" }}>
          <Typography variant="h6" color="text.secondary">
            No stocks found
          </Typography>
        </Paper>
      ) : (
        <Box>
          {filteredAndSortedScores.map((stock) => (
            <Accordion
              key={stock.symbol}
              expanded={expandedStock === stock.symbol}
              onChange={handleAccordionChange(stock.symbol)}
              sx={{ mb: 1 }}
            >
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Grid container alignItems="center" spacing={2} sx={{ width: "100%" }}>
                  <Grid item xs={12} sm={3}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                      <ScoreGauge score={Math.round(stock.composite_score)} size={70} />
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="h5" fontWeight={700}>
                          {stock.symbol}
                        </Typography>
                        <Typography variant="h6" color="primary" fontWeight={600}>
                          Score: {stock.composite_score.toFixed(1)}
                        </Typography>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                          <Typography variant="body2" color="text.secondary">
                            ${stock.current_price.toFixed(2)}
                          </Typography>
                          {formatChange(stock.price_change_1d)}
                        </Box>
                      </Box>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", justifyContent: "center" }}>
                      <Chip
                        icon={<Stars />}
                        label={`Quality: ${stock.quality_score.toFixed(1)}`}
                        size="medium"
                        color={stock.quality_score >= 80 ? "success" : stock.quality_score >= 60 ? "warning" : "error"}
                        variant="filled"
                      />
                      <Chip
                        icon={<TrendingUp />}
                        label={`Momentum: ${stock.momentum_score.toFixed(1)}`}
                        size="medium"
                        color={stock.momentum_score >= 80 ? "success" : stock.momentum_score >= 60 ? "warning" : "error"}
                        variant="filled"
                      />
                      <Chip
                        icon={<AccountBalance />}
                        label={`Value: ${stock.value_score.toFixed(1)}`}
                        size="medium"
                        color={stock.value_score >= 80 ? "success" : stock.value_score >= 60 ? "warning" : "error"}
                        variant="filled"
                      />
                      {stock.growth_score && (
                        <Chip
                          icon={<Timeline />}
                          label={`Growth: ${stock.growth_score.toFixed(1)}`}
                          size="medium"
                          color={stock.growth_score >= 80 ? "success" : stock.growth_score >= 60 ? "warning" : "error"}
                          variant="filled"
                        />
                      )}
                      {stock.relative_strength_score && (
                        <Chip
                          icon={<Bolt />}
                          label={`Rel Strength: ${stock.relative_strength_score.toFixed(1)}`}
                          size="medium"
                          color={stock.relative_strength_score >= 80 ? "success" : stock.relative_strength_score >= 60 ? "warning" : "error"}
                          variant="filled"
                        />
                      )}
                      {stock.positioning_score && (
                        <Chip
                          icon={<Group />}
                          label={`Positioning: ${stock.positioning_score.toFixed(1)}`}
                          size="medium"
                          color={stock.positioning_score >= 80 ? "success" : stock.positioning_score >= 60 ? "warning" : "error"}
                          variant="filled"
                        />
                      )}
                      {stock.sentiment_score && (
                        <Chip
                          icon={<SentimentSatisfied />}
                          label={`Sentiment: ${stock.sentiment_score.toFixed(1)}`}
                          size="medium"
                          color={stock.sentiment_score >= 80 ? "success" : stock.sentiment_score >= 60 ? "warning" : "error"}
                          variant="filled"
                        />
                      )}
                      <Chip
                        icon={<Psychology />}
                        label={`Technical: ${stock.price_change_30d?.toFixed(1) || 'N/A'}%`}
                        size="medium"
                        variant="outlined"
                      />
                      <Chip
                        icon={<Security />}
                        label={`Risk: ${stock.volatility_30d?.toFixed(1) || 'N/A'}%`}
                        size="medium"
                        variant="outlined"
                      />
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={3}>
                    <Box sx={{ textAlign: "right", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 0.5 }}>
                      {signals[stock.symbol] && (
                        <>
                          <TradingSignal
                            signal={signals[stock.symbol].signal}
                            confidence={signals[stock.symbol].confidence}
                            size="small"
                          />
                          <Typography variant="caption" color="text.secondary">
                            {new Date(signals[stock.symbol].date).toLocaleDateString()}
                          </Typography>
                        </>
                      )}
                    </Box>
                  </Grid>
                </Grid>
              </AccordionSummary>
              <AccordionDetails>
                <Box>
                  <Typography variant="h6" gutterBottom sx={{ mb: 3 }}>
                    Factor Analysis for {stock.symbol}
                  </Typography>

                  <Grid container spacing={3}>
                    {/* Momentum Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Speed sx={{ color: theme.palette.warning.main }} />
                            <Typography variant="h6">Momentum</Typography>
                            <Chip
                              label={stock.momentum_score?.toFixed(1) || 'N/A'}
                              color={stock.momentum_score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            Momentum score based on price trends across multiple timeframes
                          </Typography>
                          <Grid container spacing={2}>
                            {stock.jt_momentum_12_1 && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">JT Momentum (12-1)</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.jt_momentum_12_1.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.jt_momentum_12_1}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.warning.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.warning.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.momentum_3m && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">3-Month Momentum</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.momentum_3m.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.momentum_3m}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.warning.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.warning.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.momentum_6m && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">6-Month Momentum</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.momentum_6m.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.momentum_6m}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.warning.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.warning.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.risk_adjusted_momentum && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Risk-Adjusted Momentum</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.risk_adjusted_momentum.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.risk_adjusted_momentum}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.warning.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.warning.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Trend Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <TrendingUp sx={{ color: theme.palette.success.main }} />
                            <Typography variant="h6">Trend</Typography>
                            <Chip
                              label={stock.trend_score.toFixed(1)}
                              color={stock.trend_score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            Trend analyzes price direction relative to moving averages
                          </Typography>
                          <Grid container spacing={2}>
                            <Grid item xs={6}>
                              <Typography variant="body2" color="text.secondary">SMA 20</Typography>
                              <Typography variant="body2" fontWeight={600}>${stock.sma_20?.toFixed(2) || 'N/A'}</Typography>
                            </Grid>
                            <Grid item xs={6}>
                              <Typography variant="body2" color="text.secondary">SMA 50</Typography>
                              <Typography variant="body2" fontWeight={600}>${stock.sma_50?.toFixed(2) || 'N/A'}</Typography>
                            </Grid>
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Value Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <AccountBalance sx={{ color: theme.palette.info.main }} />
                            <Typography variant="h6">Value</Typography>
                            <Chip
                              label={stock.value_score?.toFixed(1) || 'N/A'}
                              color={stock.value_score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            Value assessment based on valuation multiples and intrinsic value
                          </Typography>
                          <Grid container spacing={2}>
                            {stock.multiples_metric && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Multiples Score</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.multiples_metric.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.multiples_metric}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.info.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.info.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.intrinsic_value && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Intrinsic Value</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.intrinsic_value.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.intrinsic_value}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.info.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.info.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.fair_value && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Fair Value</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.fair_value.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.fair_value}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.info.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.info.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Quality Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Stars sx={{ color: theme.palette.primary.main }} />
                            <Typography variant="h6">Quality</Typography>
                            <Chip
                              label={stock.quality_score?.toFixed(1) || 'N/A'}
                              color={stock.quality_score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            Quality assessment based on profitability, consistency, and growth quality
                          </Typography>
                          <Grid container spacing={2}>
                            {stock.profitability_score && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Profitability Score</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.profitability_score.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.profitability_score}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.primary.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.primary.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.consistency_score && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Consistency Score</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.consistency_score.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.consistency_score}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.primary.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.primary.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.growth_quality && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Growth Quality</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.growth_quality.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.growth_quality}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.primary.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.primary.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Technical Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Assessment sx={{ color: theme.palette.secondary.main }} />
                            <Typography variant="h6">Technical</Typography>
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            Technical analysis based on price movements and patterns
                          </Typography>
                          <Grid container spacing={2}>
                            <Grid item xs={6}>
                              <Typography variant="body2" color="text.secondary">5-Day Change</Typography>
                              <Typography variant="body2" fontWeight={600}>{stock.price_change_5d?.toFixed(2) || 'N/A'}%</Typography>
                            </Grid>
                            <Grid item xs={6}>
                              <Typography variant="body2" color="text.secondary">30-Day Change</Typography>
                              <Typography variant="body2" fontWeight={600}>{stock.price_change_30d?.toFixed(2) || 'N/A'}%</Typography>
                            </Grid>
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Risk Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <Security sx={{ color: theme.palette.error.main }} />
                            <Typography variant="h6">Risk</Typography>
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            Risk assessment based on volatility and market conditions
                          </Typography>
                          <Box>
                            <Typography variant="body2" color="text.secondary">30-Day Volatility</Typography>
                            <Typography variant="body2" fontWeight={600}>{stock.volatility_30d?.toFixed(2) || 'N/A'}%</Typography>
                          </Box>
                        </CardContent>
                      </Card>
                    </Grid>

                    {/* Growth Factor */}
                    <Grid item xs={12} md={6}>
                      <Card>
                        <CardContent>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
                            <TrendingUp sx={{ color: theme.palette.success.main }} />
                            <Typography variant="h6">Growth</Typography>
                            <Chip
                              label={stock.growth_score?.toFixed(1) || 'N/A'}
                              color={stock.growth_score >= 80 ? "success" : "warning"}
                              size="small"
                            />
                          </Box>
                          <Typography variant="body2" color="text.secondary" paragraph>
                            Growth assessment based on revenue and earnings trends
                          </Typography>
                          <Grid container spacing={2}>
                            {stock.revenue_growth_metric && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Revenue Growth</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.revenue_growth_metric.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.revenue_growth_metric}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.success.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.success.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.earnings_growth_metric && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Earnings Growth</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.earnings_growth_metric.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.earnings_growth_metric}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.success.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.success.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                            {stock.margin_expansion_metric && (
                              <Grid item xs={12}>
                                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                                  <Typography variant="body2">Margin Expansion</Typography>
                                  <Typography variant="body2" fontWeight={600}>
                                    {stock.margin_expansion_metric.toFixed(1)}
                                  </Typography>
                                </Box>
                                <LinearProgress
                                  variant="determinate"
                                  value={stock.margin_expansion_metric}
                                  sx={{
                                    height: 6,
                                    borderRadius: 3,
                                    backgroundColor: alpha(theme.palette.success.main, 0.1),
                                    "& .MuiLinearProgress-bar": {
                                      backgroundColor: theme.palette.success.main,
                                      borderRadius: 3,
                                    },
                                  }}
                                />
                              </Grid>
                            )}
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>
                  </Grid>

                  <Divider sx={{ my: 3 }} />

                  <Typography variant="body2" color="text.secondary">
                    Last Updated: {new Date(stock.lastUpdated).toLocaleDateString()}
                  </Typography>
                </Box>
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      )}

    </Container>
  );
};

export default ScoresDashboard;