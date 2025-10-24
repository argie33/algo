import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  LinearProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Alert,
  Tooltip,
  useTheme,
  alpha,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Warning,
  CheckCircle,
  Info,
  WarningAmber,
} from "@mui/icons-material";
import { getMarketInternals } from "../services/api";
import { formatPercentage } from "../utils/formatters";

const MarketInternals = () => {
  const theme = useTheme();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["marketInternals"],
    queryFn: getMarketInternals,
    refetchInterval: 60000, // Refresh every 60 seconds
    staleTime: 30000,
  });

  if (isLoading) {
    return (
      <Box display="flex" justifyContent="center" p={3}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        Failed to load market internals: {error.message}
        <br />
        <Typography
          variant="caption"
          onClick={() => refetch()}
          sx={{ cursor: "pointer", textDecoration: "underline", mt: 1 }}
        >
          Retry
        </Typography>
      </Alert>
    );
  }

  const internals = data?.data || {};

  // Helper function to get color based on value
  const getColorForValue = (value, highIsGood = true) => {
    if (highIsGood) {
      if (value >= 65) return "#10b981"; // Green
      if (value >= 55) return "#84cc16"; // Lime
      if (value >= 45) return "#f59e0b"; // Orange
      return "#ef4444"; // Red
    } else {
      if (value <= 35) return "#10b981"; // Green
      if (value <= 45) return "#84cc16"; // Lime
      if (value <= 55) return "#f59e0b"; // Orange
      return "#ef4444"; // Red
    }
  };

  // Get signal color
  const getSignalColor = () => {
    const level = internals.overextension_indicator?.level;
    if (level === "Extreme" || level === "Extreme Down") return "#dc2626"; // Red
    if (level === "Strong" || level === "Strong Down") return "#f59e0b"; // Orange
    return "#10b981"; // Green
  };

  return (
    <Box sx={{ width: "100%" }}>
      <Typography variant="h5" sx={{ mb: 3, fontWeight: 700 }}>
        📊 Market Internals & Technical Indicators
      </Typography>

      {/* Overextension Alert */}
      {internals.overextension_indicator && (
        <Card
          sx={{
            mb: 3,
            bgcolor: alpha(getSignalColor(), 0.1),
            borderLeft: `4px solid ${getSignalColor()}`,
          }}
        >
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={1}>
              {internals.overextension_indicator.level === "Extreme" ||
              internals.overextension_indicator.level === "Extreme Down" ? (
                <WarningAmber sx={{ color: getSignalColor(), fontSize: 28 }} />
              ) : internals.overextension_indicator.level === "Strong" ||
                internals.overextension_indicator.level === "Strong Down" ? (
                <Warning sx={{ color: getSignalColor(), fontSize: 28 }} />
              ) : (
                <CheckCircle sx={{ color: getSignalColor(), fontSize: 28 }} />
              )}
              <Box>
                <Typography
                  variant="h6"
                  sx={{ color: getSignalColor(), fontWeight: 700 }}
                >
                  {internals.overextension_indicator.level} Market Condition
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {internals.overextension_indicator.signal ||
                    "Market in normal trading range"}
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Market Breadth Section */}
      <Grid container spacing={3} mb={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                📈 Market Breadth
              </Typography>

              {/* Breadth Stats */}
              <Box mb={3}>
                <Box
                  display="flex"
                  justifyContent="space-between"
                  alignItems="center"
                  mb={1}
                >
                  <Typography variant="body2" color="text.secondary">
                    Advancing: {internals.market_breadth?.advancing || 0} (
                    {internals.market_breadth?.advancing_percent || "0"}%)
                  </Typography>
                  <Chip
                    icon={<TrendingUp />}
                    label="Up"
                    size="small"
                    sx={{ bgcolor: "#10b981", color: "white" }}
                  />
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={parseFloat(
                    internals.market_breadth?.advancing_percent || 0
                  )}
                  sx={{
                    height: 8,
                    mb: 2,
                    backgroundColor: alpha("#10b981", 0.2),
                    "& .MuiLinearProgress-bar": {
                      backgroundColor: "#10b981",
                    },
                  }}
                />

                <Box
                  display="flex"
                  justifyContent="space-between"
                  alignItems="center"
                  mb={1}
                >
                  <Typography variant="body2" color="text.secondary">
                    Declining: {internals.market_breadth?.declining || 0} (
                    {100 - (parseFloat(internals.market_breadth?.advancing_percent) || 0)
                      }%)
                  </Typography>
                  <Chip
                    icon={<TrendingDown />}
                    label="Down"
                    size="small"
                    sx={{ bgcolor: "#ef4444", color: "white" }}
                  />
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={100 - (parseFloat(internals.market_breadth?.advancing_percent) || 0)}
                  sx={{
                    height: 8,
                    mb: 2,
                    backgroundColor: alpha("#ef4444", 0.2),
                    "& .MuiLinearProgress-bar": {
                      backgroundColor: "#ef4444",
                    },
                  }}
                />

                <Box display="flex" justifyContent="space-between" mb={1.5}>
                  <Typography variant="caption">
                    Total Stocks: {internals.market_breadth?.total_stocks || 0}
                  </Typography>
                  <Typography variant="caption">
                    A/D Ratio:{" "}
                    {internals.market_breadth?.decline_advance_ratio || "N/A"}
                  </Typography>
                </Box>
              </Box>

              {/* Breadth Percentile */}
              <Paper sx={{ p: 2, bgcolor: alpha(theme.palette.primary.main, 0.05) }}>
                <Typography variant="caption" color="text.secondary">
                  Breadth Percentile Rank
                </Typography>
                <Typography
                  variant="h4"
                  sx={{
                    color: getColorForValue(
                      internals.market_extremes?.breadth_rank || 50
                    ),
                    fontWeight: 700,
                  }}
                >
                  {internals.market_extremes?.breadth_rank || 50}%
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Current vs 90-day range
                </Typography>
              </Paper>
            </CardContent>
          </Card>
        </Grid>

        {/* Moving Average Analysis */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                📍 Stocks Above Moving Averages
              </Typography>

              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: alpha(theme.palette.primary.main, 0.05) }}>
                      <TableCell>MA Period</TableCell>
                      <TableCell align="right">Count</TableCell>
                      <TableCell align="right">Percentage</TableCell>
                      <TableCell align="right">Avg Distance</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      <TableCell>
                        <strong>20-Day SMA</strong>
                      </TableCell>
                      <TableCell align="right">
                        {internals.moving_average_analysis?.above_sma20?.count || 0}
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={`${internals.moving_average_analysis?.above_sma20?.percent || "N/A"}%`}
                          size="small"
                          sx={{
                            bgcolor: alpha(
                              getColorForValue(
                                parseFloat(
                                  internals.moving_average_analysis?.above_sma20
                                    ?.percent || 0
                                )
                              ),
                              0.2
                            ),
                            color: getColorForValue(
                              parseFloat(
                                internals.moving_average_analysis?.above_sma20
                                  ?.percent || 0
                              )
                            ),
                            fontWeight: 600,
                          }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="caption">
                          {internals.moving_average_analysis?.above_sma20
                            ?.avg_distance_pct || "0"}%
                        </Typography>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>
                        <strong>50-Day SMA</strong>
                      </TableCell>
                      <TableCell align="right">
                        {internals.moving_average_analysis?.above_sma50?.count || 0}
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={`${internals.moving_average_analysis?.above_sma50?.percent || "N/A"}%`}
                          size="small"
                          sx={{
                            bgcolor: alpha(
                              getColorForValue(
                                parseFloat(
                                  internals.moving_average_analysis?.above_sma50
                                    ?.percent || 0
                                )
                              ),
                              0.2
                            ),
                            color: getColorForValue(
                              parseFloat(
                                internals.moving_average_analysis?.above_sma50
                                  ?.percent || 0
                              )
                            ),
                            fontWeight: 600,
                          }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="caption">
                          {internals.moving_average_analysis?.above_sma50
                            ?.avg_distance_pct || "0"}%
                        </Typography>
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>
                        <strong>200-Day SMA</strong>
                      </TableCell>
                      <TableCell align="right">
                        {internals.moving_average_analysis?.above_sma200
                          ?.count || 0}
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={`${internals.moving_average_analysis?.above_sma200?.percent || "N/A"}%`}
                          size="small"
                          sx={{
                            bgcolor: alpha(
                              getColorForValue(
                                parseFloat(
                                  internals.moving_average_analysis?.above_sma200
                                    ?.percent || 0
                                )
                              ),
                              0.2
                            ),
                            color: getColorForValue(
                              parseFloat(
                                internals.moving_average_analysis?.above_sma200
                                  ?.percent || 0
                              )
                            ),
                            fontWeight: 600,
                          }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="caption">
                          {internals.moving_average_analysis?.above_sma200
                            ?.avg_distance_pct || "0"}%
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

      {/* Market Extremes & Positioning */}
      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                📊 Market Extremes (90-Day Analysis)
              </Typography>

              <Box mb={2}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Breadth Distribution
                </Typography>
                <Box display="flex" justifyContent="space-between" my={1}>
                  <Typography variant="caption">Min</Typography>
                  <Typography variant="caption">25th %ile</Typography>
                  <Typography variant="caption">Median</Typography>
                  <Typography variant="caption">75th %ile</Typography>
                  <Typography variant="caption">Max</Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={
                    ((parseFloat(internals.market_extremes?.current_breadth_percentile || 50) -
                      parseFloat(internals.market_extremes?.percentile_25 || 0)) /
                      (parseFloat(internals.market_extremes?.percentile_75 || 100) -
                        parseFloat(internals.market_extremes?.percentile_25 || 0))) *
                    100
                  }
                  sx={{
                    height: 8,
                    backgroundColor: alpha(theme.palette.primary.main, 0.2),
                    "& .MuiLinearProgress-bar": {
                      backgroundColor: theme.palette.primary.main,
                    },
                  }}
                />
              </Box>

              <Box display="grid" gridTemplateColumns="1fr 1fr" gap={2}>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Current Breadth
                  </Typography>
                  <Typography
                    variant="h5"
                    sx={{
                      color: getColorForValue(
                        parseFloat(
                          internals.market_extremes?.current_breadth_percentile || 50
                        )
                      ),
                      fontWeight: 700,
                    }}
                  >
                    {internals.market_extremes?.current_breadth_percentile || "0"}%
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    StdDev from Mean
                  </Typography>
                  <Typography
                    variant="h5"
                    sx={{
                      color:
                        Math.abs(
                          parseFloat(internals.market_extremes?.stddev_from_mean || 0)
                        ) > 2
                          ? "#dc2626"
                          : Math.abs(
                              parseFloat(internals.market_extremes?.stddev_from_mean || 0)
                            ) > 1
                          ? "#f59e0b"
                          : "#10b981",
                      fontWeight: 700,
                    }}
                  >
                    {internals.market_extremes?.stddev_from_mean || "0"}σ
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    30-Day Average
                  </Typography>
                  <Typography variant="h6">
                    {internals.market_extremes?.avg_breadth_30d || "0"}%
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    30-Day StdDev
                  </Typography>
                  <Typography variant="h6">
                    {internals.market_extremes?.stddev_breadth_30d || "0"}%
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Positioning Metrics */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                💼 Positioning & Sentiment
              </Typography>

              <Box mb={2}>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                  Retail Sentiment (AAII)
                </Typography>
                <Box display="flex" gap={1} mb={2}>
                  <Chip
                    label={`Bullish: ${internals.positioning_metrics?.retail_sentiment?.aaii_bullish || "0"}%`}
                    size="small"
                    sx={{
                      bgcolor: alpha("#10b981", 0.2),
                      color: "#10b981",
                      fontWeight: 600,
                    }}
                  />
                  <Chip
                    label={`Bearish: ${internals.positioning_metrics?.retail_sentiment?.aaii_bearish || "0"}%`}
                    size="small"
                    sx={{
                      bgcolor: alpha("#ef4444", 0.2),
                      color: "#ef4444",
                      fontWeight: 600,
                    }}
                  />
                </Box>
              </Box>

              <Box mb={2}>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                  Professional Sentiment (NAAIM)
                </Typography>
                <Box display="flex" gap={1} mb={2}>
                  <Chip
                    label={`Bullish: ${internals.positioning_metrics?.professional_sentiment?.naaim_bullish || "0"}%`}
                    size="small"
                    sx={{
                      bgcolor: alpha("#3b82f6", 0.2),
                      color: "#3b82f6",
                      fontWeight: 600,
                    }}
                  />
                  <Chip
                    label={`Bearish: ${internals.positioning_metrics?.professional_sentiment?.naaim_bearish || "0"}%`}
                    size="small"
                    sx={{
                      bgcolor: alpha("#6b7280", 0.2),
                      color: "#6b7280",
                      fontWeight: 600,
                    }}
                  />
                </Box>
              </Box>

              <Box mb={2}>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                  Institutional Positioning (30-Day)
                </Typography>
                <Box display="grid" gridTemplateColumns="1fr 1fr" gap={2}>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Avg Ownership %
                    </Typography>
                    <Typography variant="h6">
                      {internals.positioning_metrics?.institutional?.avg_ownership_pct ||
                        "0"}
                      %
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Avg Short Interest
                    </Typography>
                    <Typography variant="h6">
                      {internals.positioning_metrics?.institutional?.avg_short_interest ||
                        "0"}
                      %
                    </Typography>
                  </Box>
                </Box>
              </Box>

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
                  Fear & Greed Index
                </Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Typography variant="h5" sx={{ fontWeight: 700 }}>
                    {internals.positioning_metrics?.fear_greed_index || "50"}
                  </Typography>
                  <Chip
                    label={
                      parseFloat(
                        internals.positioning_metrics?.fear_greed_index || 50
                      ) > 75
                        ? "Extreme Greed"
                        : parseFloat(
                            internals.positioning_metrics?.fear_greed_index || 50
                          ) > 55
                        ? "Greed"
                        : parseFloat(
                            internals.positioning_metrics?.fear_greed_index || 50
                          ) < 25
                        ? "Extreme Fear"
                        : parseFloat(
                            internals.positioning_metrics?.fear_greed_index || 50
                          ) < 45
                        ? "Fear"
                        : "Neutral"
                    }
                    size="small"
                    sx={{
                      bgcolor: alpha(
                        parseFloat(
                          internals.positioning_metrics?.fear_greed_index || 50
                        ) > 55
                          ? "#ef4444"
                          : "#10b981",
                        0.2
                      ),
                      color:
                        parseFloat(
                          internals.positioning_metrics?.fear_greed_index || 50
                        ) > 55
                          ? "#ef4444"
                          : "#10b981",
                      fontWeight: 600,
                    }}
                  />
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Data Info */}
      <Typography variant="caption" color="text.secondary" sx={{ mt: 3, display: "block" }}>
        <Info sx={{ fontSize: 14, mr: 0.5, verticalAlign: "middle" }} />
        Data updated every 60 seconds. Last update:{" "}
        {new Date(data?.timestamp || Date.now()).toLocaleTimeString()}
      </Typography>
    </Box>
  );
};

export default MarketInternals;
