import React, { useState } from "react";
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
  Paper,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  LinearProgress,
  IconButton,
  InputAdornment,
} from "@mui/material";
import {
  Search, TrendingUp, TrendingDown, Timeline, Refresh, BarChart, FilterList, AccessTime, ErrorOutline } from "@mui/icons-material";
import { formatCurrency } from "../utils/formatters";
import { getApiConfig } from "../services/api";

const PatternRecognition = () => {
  const { apiUrl: API_BASE } = getApiConfig();
  const [tabValue, setTabValue] = useState(0);
  const [searchSymbol, setSearchSymbol] = useState("");
  const [selectedTimeframe, setSelectedTimeframe] = useState("1D");
  const [confidenceFilter, setConfidenceFilter] = useState(75);
  const [selectedPattern, setSelectedPattern] = useState("all");

  // Default watchlist symbols for pattern analysis
  const defaultSymbols = [
    "AAPL",
    "TSLA",
    "NVDA",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "NFLX",
    "BABA",
    "PLTR",
  ];

  // Fetch patterns data using React Query with robust logging
  const {
    data: patternsData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: [
      "patterns",
      selectedTimeframe,
      confidenceFilter,
      selectedPattern,
    ],
    queryFn: async () => {
      logger.info("Fetching patterns data for multiple symbols", {
        symbols: defaultSymbols.length,
        timeframe: selectedTimeframe,
        confidence: confidenceFilter,
        pattern: selectedPattern,
      });

      try {
        // Fetch patterns for multiple symbols in parallel
        const symbolRequests = defaultSymbols.map(async (symbol) => {
          const url = `${API_BASE}/api/technical/patterns/${symbol}?timeframe=${selectedTimeframe}&limit=5`;

          try {
            const response = await fetch(url);
            if (response.ok) {
              const data = await response.json();
              // Add symbol to each pattern for display
              return (data.patterns || []).map((pattern) => ({
                ...pattern,
                symbol: symbol,
              }));
            } else {
              logger.warn(`Failed to fetch patterns for ${symbol}`, {
                status: response.status,
              });
              return [];
            }
          } catch (error) {
            logger.warn(`Network error for ${symbol}`, error);
            return [];
          }
        });

        const allPatternArrays = await Promise.all(symbolRequests);
        const allPatterns = allPatternArrays.flat();

        // Filter patterns based on user selections
        let filteredPatterns = allPatterns.filter((pattern) => {
          // Confidence filter
          if ((pattern.confidence || 0) * 100 < confidenceFilter) return false;

          // Pattern type filter
          if (selectedPattern !== "all") {
            if (
              selectedPattern === "bullish" &&
              pattern.direction !== "bullish"
            )
              return false;
            if (
              selectedPattern === "bearish" &&
              pattern.direction !== "bearish"
            )
              return false;
            if (
              selectedPattern === "reversal" &&
              !pattern.type.includes("double")
            )
              return false;
            if (
              selectedPattern === "continuation" &&
              !pattern.type.includes("flag")
            )
              return false;
          }

          return true;
        });

        // Sort by confidence descending
        filteredPatterns.sort(
          (a, b) => (b.confidence || 0) - (a.confidence || 0)
        );

        logger.info("Successfully fetched and filtered patterns data", {
          totalPatterns: allPatterns.length,
          filteredPatterns: filteredPatterns.length,
          symbols: defaultSymbols.length,
        });

        return {
          success: true,
          data: filteredPatterns,
          metadata: {
            totalPatterns: allPatterns.length,
            filteredPatterns: filteredPatterns.length,
            symbolsAnalyzed: defaultSymbols.length,
          },
        };
      } catch (fetchError) {
        logger.error("Network error fetching patterns", fetchError);
        throw fetchError;
      }
    },
    refetchInterval: 300000, // Refresh every 5 minutes
    staleTime: 60000, // Consider data stale after 1 minute
    onError: (err) => {
      logger.error("React Query error", err, {
        timeframe: selectedTimeframe,
        confidence: confidenceFilter,
        pattern: selectedPattern,
      });
    },
    onSuccess: (data) => {
      logger.debug("React Query success", {
        patternCount: data?.data?.length || 0,
        timestamp: new Date().toISOString(),
      });
    },
  });

  // Analyze specific symbol with robust logging
  const analyzeSymbol = async () => {
    if (!searchSymbol.trim()) {
      logger.warn("Attempted to analyze symbol with empty input");
      return;
    }

    const symbol = searchSymbol.toUpperCase();
    const url = `${API_BASE}/api/technical/patterns/${symbol}?timeframe=${selectedTimeframe}`;

    logger.info("Analyzing specific symbol", {
      symbol,
      timeframe: selectedTimeframe,
      url,
    });

    try {
      const response = await fetch(url);

      if (response.ok) {
        const data = await response.json();
        logger.info("Symbol analysis completed successfully", {
          symbol,
          patternsFound: data?.data?.patterns?.length || 0,
          response: data,
        });

        // Trigger a refetch to include the new analysis
        refetch();
      } else {
        const errorText = await response.text();
        logger.error(
          "Symbol analysis failed",
          new Error(`HTTP ${response.status}`),
          {
            symbol,
            url,
            status: response.status,
            statusText: response.statusText,
            responseBody: errorText,
          }
        );
      }
    } catch (error) {
      logger.error("Network error during symbol analysis", error, {
        symbol,
        url,
      });
    }
  };

  const getPatternColor = (pattern) => {
    const bullishPatterns = [
      "bullish_flag",
      "cup_handle",
      "ascending_triangle",
      "double_bottom",
      "inverse_head_shoulders",
    ];
    const bearishPatterns = [
      "bearish_flag",
      "head_shoulders",
      "descending_triangle",
      "double_top",
      "falling_wedge",
    ];

    if (bullishPatterns.some((p) => pattern.includes(p))) return "success";
    if (bearishPatterns.some((p) => pattern.includes(p))) return "error";
    return "info";
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 90) return "success";
    if (confidence >= 75) return "info";
    if (confidence >= 60) return "warning";
    return "error";
  };

  const formatPatternName = (pattern) => {
    return pattern
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  };

  const getPatternIcon = (bias) => {
    if (bias === "bullish")
      return <TrendingUp color="success" fontSize="small" />;
    if (bias === "bearish")
      return <TrendingDown color="error" fontSize="small" />;
    return <BarChart color="primary" fontSize="small" />;
  };

  const patterns = patternsData?.data || [];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h3"
          component="h1"
          gutterBottom
          sx={{ fontWeight: 700, color: "primary.main" }}
        >
          🔍 AI Pattern Recognition
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Advanced technical pattern detection using machine learning algorithms
        </Typography>
      </Box>

      {/* Search and Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={3} alignItems="flex-end">
            <Grid item xs={12} md={3}>
              <TextField
                fullWidth
                label="Symbol"
                placeholder="Enter symbol..."
                value={searchSymbol}
                onChange={(e) => setSearchSymbol(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && analyzeSymbol()}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton onClick={analyzeSymbol} disabled={isLoading}>
                        <Search />
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>

            <Grid item xs={12} md={2}>
              <FormControl fullWidth>
                <InputLabel>Timeframe</InputLabel>
                <Select
                  value={selectedTimeframe}
                  label="Timeframe"
                  onChange={(e) => setSelectedTimeframe(e.target.value)}
                >
                  <MenuItem value="1D">1 Day</MenuItem>
                  <MenuItem value="1W">1 Week</MenuItem>
                  <MenuItem value="1M">1 Month</MenuItem>
                  <MenuItem value="3M">3 Months</MenuItem>
                  <MenuItem value="6M">6 Months</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} md={2}>
              <FormControl fullWidth>
                <InputLabel>Pattern Type</InputLabel>
                <Select
                  value={selectedPattern}
                  label="Pattern Type"
                  onChange={(e) => setSelectedPattern(e.target.value)}
                >
                  <MenuItem value="all">All Patterns</MenuItem>
                  <MenuItem value="bullish">Bullish Only</MenuItem>
                  <MenuItem value="bearish">Bearish Only</MenuItem>
                  <MenuItem value="reversal">Reversal Patterns</MenuItem>
                  <MenuItem value="continuation">
                    Continuation Patterns
                  </MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} md={3}>
              <Typography variant="body2" gutterBottom>
                Min Confidence: {confidenceFilter}%
              </Typography>
              <Slider
                value={confidenceFilter}
                onChange={(e, newValue) => setConfidenceFilter(newValue)}
                min={50}
                max={99}
                step={1}
                valueLabelDisplay="auto"
                valueLabelFormat={(value) => `${value}%`}
              />
            </Grid>

            <Grid item xs={12} md={2}>
              <Button
                fullWidth
                variant="contained"
                onClick={refetch}
                disabled={isLoading}
                startIcon={<FilterList />}
              >
                Scan Market
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Error Handling */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Failed to Load Pattern Data
          </Typography>
          <Typography variant="body2" gutterBottom>
            Error: {error.message}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            API Endpoint: {API_BASE}/api/technical/patterns
          </Typography>
          <Button
            variant="outlined"
            size="small"
            onClick={refetch}
            sx={{ mt: 1 }}
            startIcon={<Refresh />}
          >
            Retry
          </Button>
        </Alert>
      )}

      {/* Loading State */}
      {isLoading && !patterns.length && (
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="300px"
        >
          <Box textAlign="center">
            <CircularProgress size={60} />
            <Typography variant="h6" sx={{ mt: 2 }}>
              Analyzing Market Patterns...
            </Typography>
          </Box>
        </Box>
      )}

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
        <Tabs
          value={tabValue}
          onChange={(e, newValue) => setTabValue(newValue)}
        >
          <Tab
            label={`Detected Patterns (${patterns.length})`}
            icon={<Timeline />}
          />
          <Tab label="Bullish Signals" icon={<TrendingUp />} />
          <Tab label="Bearish Signals" icon={<TrendingDown />} />
          <Tab label="Pattern Analytics" icon={<BarChart />} />
        </Tabs>
      </Box>

      {/* Tab Content */}
      {tabValue === 0 && (
        <Box>
          {!isLoading && patterns.length > 0 && (
            <Grid container spacing={3}>
              {patterns.map((pattern, index) => (
                <Grid item xs={12} md={6} lg={4} key={index}>
                  <Card sx={{ height: "100%", "&:hover": { boxShadow: 6 } }}>
                    <CardHeader
                      title={
                        <Box
                          display="flex"
                          alignItems="center"
                          justifyContent="space-between"
                        >
                          <Box display="flex" alignItems="center" gap={1}>
                            <Typography variant="h6" fontWeight="bold">
                              {pattern.symbol}
                            </Typography>
                            {getPatternIcon(pattern.direction)}
                          </Box>
                          <Chip
                            label={`${Math.round((pattern.confidence || 0) * 100)}%`}
                            color={getConfidenceColor(
                              Math.round((pattern.confidence || 0) * 100)
                            )}
                            size="small"
                          />
                        </Box>
                      }
                      subheader={
                        <Box display="flex" alignItems="center" gap={1} mt={1}>
                          <Chip
                            label={formatPatternName(pattern.type)}
                            color={getPatternColor(pattern.type)}
                            size="small"
                          />
                          <Typography variant="caption" color="text.secondary">
                            {pattern.timeframe}
                          </Typography>
                        </Box>
                      }
                      sx={{ pb: 1 }}
                    />
                    <CardContent>
                      {/* Pattern Chart Placeholder */}
                      <Box
                        sx={{
                          height: 120,
                          bgcolor: "grey.50",
                          borderRadius: 1,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          mb: 2,
                        }}
                      >
                        <Typography variant="body2" color="text.secondary">
                          Pattern Visualization
                        </Typography>
                      </Box>

                      {/* Pattern Details */}
                      <Grid container spacing={1} sx={{ mb: 2 }}>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">
                            Entry:
                          </Typography>
                          <Typography variant="body2" fontWeight="medium">
                            {formatCurrency(pattern.entry_price || 0)}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">
                            Target:
                          </Typography>
                          <Typography variant="body2" fontWeight="medium">
                            {formatCurrency(pattern.target_price || 0)}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">
                            Stop Loss:
                          </Typography>
                          <Typography variant="body2" fontWeight="medium">
                            {formatCurrency(pattern.stop_loss || 0)}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="caption" color="text.secondary">
                            R/R:
                          </Typography>
                          <Typography variant="body2" fontWeight="medium">
                            {pattern.riskReward || "N/A"}
                          </Typography>
                        </Grid>
                      </Grid>

                      {/* Pattern Strength */}
                      <Box sx={{ mb: 2 }}>
                        <Box
                          display="flex"
                          justifyContent="space-between"
                          mb={0.5}
                        >
                          <Typography variant="caption" color="text.secondary">
                            Pattern Strength
                          </Typography>
                          <Typography variant="caption" fontWeight="medium">
                            {pattern.strength || 0}%
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={pattern.strength || 0}
                          sx={{ height: 6, borderRadius: 3 }}
                        />
                      </Box>

                      {/* Detection Time */}
                      <Box display="flex" alignItems="center" gap={0.5}>
                        <AccessTime fontSize="small" color="action" />
                        <Typography variant="caption" color="text.secondary">
                          Detected{" "}
                          {pattern.detected_at
                            ? new Date(pattern.detected_at).toLocaleDateString()
                            : "recently"}
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}

          {!isLoading && patterns.length === 0 && (
            <Card>
              <CardContent sx={{ textAlign: "center", py: 8 }}>
                <ErrorOutline
                  sx={{ fontSize: 64, color: "text.secondary", mb: 2 }}
                />
                <Typography variant="h6" gutterBottom>
                  No Patterns Found
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Try adjusting your filters or scanning a different timeframe.
                </Typography>
              </CardContent>
            </Card>
          )}
        </Box>
      )}

      {tabValue === 1 && (
        <Box>
          <Grid container spacing={3}>
            {patterns
              .filter((p) => p.direction === "bullish")
              .map((pattern, index) => (
                <Grid item xs={12} md={6} lg={4} key={index}>
                  <Card
                    sx={{
                      border: "2px solid",
                      borderColor: "success.light",
                      bgcolor: "success.50",
                      "&:hover": { boxShadow: 6 },
                    }}
                  >
                    <CardHeader
                      title={
                        <Box
                          display="flex"
                          alignItems="center"
                          justifyContent="space-between"
                        >
                          <Typography
                            variant="h6"
                            fontWeight="bold"
                            color="success.dark"
                          >
                            {pattern.symbol}
                          </Typography>
                          <TrendingUp color="success" />
                        </Box>
                      }
                      subheader={
                        <Chip
                          label={formatPatternName(pattern.type)}
                          sx={{
                            bgcolor: "success.100",
                            color: "success.dark",
                            border: "1px solid",
                            borderColor: "success.300",
                          }}
                          size="small"
                        />
                      }
                    />
                    <CardContent>
                      <Box display="flex" justifyContent="space-between" mb={1}>
                        <Typography variant="body2" color="success.dark">
                          Upside Potential:
                        </Typography>
                        <Typography
                          variant="body2"
                          fontWeight="bold"
                          color="success.dark"
                        >
                          {pattern.target_price && pattern.entry_price
                            ? (
                                ((pattern.target_price - pattern.entry_price) /
                                  pattern.entry_price) *
                                100
                              ).toFixed(1)
                            : "N/A"}
                          %
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="space-between" mb={1}>
                        <Typography variant="body2" color="success.dark">
                          Confidence:
                        </Typography>
                        <Typography
                          variant="body2"
                          fontWeight="bold"
                          color="success.dark"
                        >
                          {Math.round((pattern.confidence || 0) * 100)}%
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="space-between">
                        <Typography variant="body2" color="success.dark">
                          Risk/Reward:
                        </Typography>
                        <Typography
                          variant="body2"
                          fontWeight="bold"
                          color="success.dark"
                        >
                          {pattern.riskReward}
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
          </Grid>
          {patterns.filter((p) => p.direction === "bullish").length === 0 && (
            <Alert severity="info">
              No bullish patterns found with current filters.
            </Alert>
          )}
        </Box>
      )}

      {tabValue === 2 && (
        <Box>
          <Grid container spacing={3}>
            {patterns
              .filter((p) => p.direction === "bearish")
              .map((pattern, index) => (
                <Grid item xs={12} md={6} lg={4} key={index}>
                  <Card
                    sx={{
                      border: "2px solid",
                      borderColor: "error.light",
                      bgcolor: "error.50",
                      "&:hover": { boxShadow: 6 },
                    }}
                  >
                    <CardHeader
                      title={
                        <Box
                          display="flex"
                          alignItems="center"
                          justifyContent="space-between"
                        >
                          <Typography
                            variant="h6"
                            fontWeight="bold"
                            color="error.dark"
                          >
                            {pattern.symbol}
                          </Typography>
                          <TrendingDown color="error" />
                        </Box>
                      }
                      subheader={
                        <Chip
                          label={formatPatternName(pattern.type)}
                          sx={{
                            bgcolor: "error.100",
                            color: "error.dark",
                            border: "1px solid",
                            borderColor: "error.300",
                          }}
                          size="small"
                        />
                      }
                    />
                    <CardContent>
                      <Box display="flex" justifyContent="space-between" mb={1}>
                        <Typography variant="body2" color="error.dark">
                          Downside Risk:
                        </Typography>
                        <Typography
                          variant="body2"
                          fontWeight="bold"
                          color="error.dark"
                        >
                          {pattern.entry_price && pattern.target_price
                            ? (
                                ((pattern.entry_price - pattern.target_price) /
                                  pattern.entry_price) *
                                100
                              ).toFixed(1)
                            : "N/A"}
                          %
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="space-between" mb={1}>
                        <Typography variant="body2" color="error.dark">
                          Confidence:
                        </Typography>
                        <Typography
                          variant="body2"
                          fontWeight="bold"
                          color="error.dark"
                        >
                          {Math.round((pattern.confidence || 0) * 100)}%
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="space-between">
                        <Typography variant="body2" color="error.dark">
                          Risk/Reward:
                        </Typography>
                        <Typography
                          variant="body2"
                          fontWeight="bold"
                          color="error.dark"
                        >
                          {pattern.riskReward}
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
          </Grid>
          {patterns.filter((p) => p.direction === "bearish").length === 0 && (
            <Alert severity="info">
              No bearish patterns found with current filters.
            </Alert>
          )}
        </Box>
      )}

      {tabValue === 3 && (
        <Box>
          <Grid container spacing={3} mb={4}>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent sx={{ textAlign: "center", py: 3 }}>
                  <Typography
                    variant="h4"
                    fontWeight="bold"
                    color="success.main"
                    gutterBottom
                  >
                    {patterns.filter((p) => p.direction === "bullish").length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Bullish Patterns
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent sx={{ textAlign: "center", py: 3 }}>
                  <Typography
                    variant="h4"
                    fontWeight="bold"
                    color="error.main"
                    gutterBottom
                  >
                    {patterns.filter((p) => p.direction === "bearish").length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Bearish Patterns
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent sx={{ textAlign: "center", py: 3 }}>
                  <Typography
                    variant="h4"
                    fontWeight="bold"
                    color="primary.main"
                    gutterBottom
                  >
                    {patterns.filter((p) => (p.confidence || 0) >= 0.9).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    High Confidence
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent sx={{ textAlign: "center", py: 3 }}>
                  <Typography variant="h4" fontWeight="bold" gutterBottom>
                    {patterns.length > 0
                      ? (
                          (patterns.reduce(
                            (sum, p) => sum + (p.confidence || 0),
                            0
                          ) /
                            patterns.length) *
                          100
                        ).toFixed(0)
                      : 0}
                    %
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Avg Confidence
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Card>
            <CardHeader
              title="Pattern Performance Statistics"
              avatar={<BarChart color="primary" />}
            />
            <CardContent>
              <Alert severity="info" sx={{ mb: 3 }}>
                <Typography variant="body2">
                  Pattern recognition uses advanced machine learning algorithms
                  trained on historical market data. Results should be used in
                  conjunction with other analysis methods.
                </Typography>
              </Alert>

              <Grid container spacing={4}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Pattern Distribution
                  </Typography>
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Pattern Type</TableCell>
                          <TableCell align="right">Count</TableCell>
                          <TableCell align="right">Percentage</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {[
                          "bullish_flag",
                          "ascending_triangle",
                          "cup_and_handle",
                          "double_bottom",
                          "head_and_shoulders",
                        ].map((patternType) => {
                          const count = patterns.filter(
                            (p) => p.type === patternType
                          ).length;
                          const percentage =
                            patterns.length > 0
                              ? ((count / patterns.length) * 100).toFixed(1)
                              : 0;
                          return (
                            <TableRow key={patternType}>
                              <TableCell>
                                {formatPatternName(patternType)}
                              </TableCell>
                              <TableCell align="right">{count}</TableCell>
                              <TableCell align="right">{percentage}%</TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Confidence Distribution
                  </Typography>
                  <Box>
                    {[
                      { label: "Very High (90%+)", min: 90, color: "success" },
                      {
                        label: "High (80-89%)",
                        min: 80,
                        max: 89,
                        color: "info",
                      },
                      {
                        label: "Medium (70-79%)",
                        min: 70,
                        max: 79,
                        color: "warning",
                      },
                      { label: "Low (<70%)", max: 69, color: "error" },
                    ].map((range, index) => {
                      const count = patterns.filter((p) => {
                        const conf = (p.confidence || 0) * 100; // Convert to percentage
                        if (range.min && range.max)
                          return conf >= range.min && conf <= range.max;
                        if (range.min) return conf >= range.min;
                        if (range.max) return conf <= range.max;
                        return false;
                      }).length;

                      return (
                        <Box
                          key={index}
                          display="flex"
                          justifyContent="space-between"
                          alignItems="center"
                          py={1}
                        >
                          <Typography variant="body2">{range.label}</Typography>
                          <Chip
                            label={count}
                            color={range.color}
                            size="small"
                            variant="outlined"
                          />
                        </Box>
                      );
                    })}
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Box>
      )}
    </Container>
  );
};

// Robust logging for troubleshooting
const logger = {
  info: (message, data) => {
    console.log(`[PatternRecognition] ${message}`, data);
  },
  error: (message, error, context) => {
    console.error(`[PatternRecognition] ${message}`, {
      error: error?.message || error,
      stack: error?.stack,
      context,
    });
  },
  warn: (message, data) => {
    console.warn(`[PatternRecognition] ${message}`, data);
  },
  debug: (message, data) => {
    if (process.env.NODE_ENV === "development") {
      console.debug(`[PatternRecognition] ${message}`, data);
    }
  },
};

export default PatternRecognition;
