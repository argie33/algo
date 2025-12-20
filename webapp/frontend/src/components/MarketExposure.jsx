import React, { useMemo } from "react";
import {
  Box,
  Card,
  CardContent,
  Grid,
  LinearProgress,
  Paper,
  Typography,
  Tooltip,
  Chip,
  Stack,
  alpha,
  useTheme,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  Warning,
  CheckCircle,
  Info,
} from "@mui/icons-material";

/**
 * Market Exposure Component
 *
 * Provides market exposure recommendations based on market conditions.
 * Helps traders determine what percentage of their portfolio to expose
 * to the market based on technical indicators and market breadth.
 *
 * Exposure Levels:
 * - Aggressive (80-100%): Strong uptrend, positive breadth
 * - Moderate (50-80%): Mixed signals, selective buying
 * - Conservative (20-50%): Caution, market weakness
 * - Defensive (0-20%): Major downtrend, distribution
 */
const MarketExposure = ({ marketData, breadthData, distributionDaysData }) => {
  const theme = useTheme();

  // Calculate exposure score based on market conditions
  const exposureScore = useMemo(() => {
    let score = 50; // Neutral baseline (50%)
    let signals = [];

    // CRITICAL: Return null/error if essential data is missing (no fake defaults)
    if (!marketData || !breadthData || !distributionDaysData) {
      return { score: null, level: "No Data", signals: [], breakdown: {}, error: "Missing required market data" };
    }

    const breakdown = {};

    // ===== FORMULA COMPONENTS =====
    // Simple formula: Score = Base + Breadth + Sentiment + Distribution

    // 1. MARKET BREADTH (±30 points)
    // Simple logic: Advancing/Declining ratio tells us market health
    const breadthInfo = breadthData?.data || breadthData;
    if (!breadthInfo || breadthInfo.advancing === null || breadthInfo.declining === null) {
      return { score: null, level: "No Data", signals: [], breakdown: {}, error: "Missing breadth data" };
    }
    const advancers = parseInt(breadthInfo.advancing);
    const decliners = parseInt(breadthInfo.declining);
    const total = advancers + decliners;

    // Return error if total stocks is 0 (no market data)
    if (total === 0) {
      return { score: null, level: "No Data", signals: [], breakdown: {}, error: "No market breadth data available" };
    }

    let breadthScore = 0;
    if (total > 0) {
      const advancePercent = (advancers / total) * 100;
      // If >60% advancing = bullish, <40% = bearish
      breadthScore = (advancePercent - 50) * 0.6; // Max ±30 points

      if (advancePercent > 65) {
        signals.push({ label: "Strong Breadth", color: "success", icon: "📈" });
      } else if (advancePercent > 55) {
        signals.push({ label: "Positive Breadth", color: "success", icon: "📊" });
      } else if (advancePercent < 35) {
        signals.push({ label: "Weak Breadth", color: "error", icon: "📉" });
      } else if (advancePercent < 45) {
        signals.push({ label: "Declining Breadth", color: "warning", icon: "⚠️" });
      }
    }
    breakdown.breadth = breadthScore;
    score += breadthScore;

    // 2. SENTIMENT / INDEX PERFORMANCE (±20 points)
    // NOTE: Indices data removed from new API, use breadth-only scoring
    let sentimentScore = 0;
    const indices = marketData?.data?.indices;

    // If no index data available, use neutral sentiment score (0 points)
    if (!indices || !Array.isArray(indices) || indices.length === 0) {
      // No index data - skip this component of the score
      sentimentScore = 0;
    } else {
      const spxIndex = indices.find((i) => i.symbol === "^GSPC");

      if (spxIndex && spxIndex.changePercent !== null && spxIndex.changePercent !== undefined) {
        // Simple: +1% index move = +6.67 points (max ±20)
        sentimentScore = spxIndex.changePercent * 6.67;

        if (spxIndex.changePercent > 2) {
          signals.push({ label: "Strong Market Up", color: "success", icon: "🟢" });
        } else if (spxIndex.changePercent > 0.5) {
          signals.push({ label: "Market Up", color: "success", icon: "📈" });
        } else if (spxIndex.changePercent < -2) {
          signals.push({ label: "Market Down", color: "error", icon: "🔴" });
        } else if (spxIndex.changePercent < -0.5) {
          signals.push({ label: "Market Declining", color: "warning", icon: "📉" });
        }
      }
    }
    breakdown.sentiment = sentimentScore;
    score += sentimentScore;

    // 3. DISTRIBUTION DAYS (−30 points max)
    // Too many distribution days = market weakness
    let distributionScore = 0;
    const distributionDaysData_obj = distributionDaysData || {};
    // Get S&P 500 distribution days count (or fall back to first available index)
    const recentDistribution = parseInt(
      distributionDaysData_obj["^GSPC"]?.count ||
      distributionDaysData_obj["^IXIC"]?.count ||
      distributionDaysData_obj["^DJI"]?.count ||
      0
    ) || 0;

    if (recentDistribution >= 6) {
      distributionScore = -30; // Maximum penalty
      signals.push({ label: "High Distribution ⚠️", color: "error", icon: "⛔" });
    } else if (recentDistribution >= 4) {
      distributionScore = -20;
      signals.push({ label: `${recentDistribution} Distribution Days`, color: "error", icon: "⛔" });
    } else if (recentDistribution >= 2) {
      distributionScore = -10;
      signals.push({ label: `${recentDistribution} Distribution Days`, color: "warning", icon: "⚠️" });
    } else if (recentDistribution === 1) {
      distributionScore = -5;
      signals.push({ label: "1 Distribution Day", color: "warning", icon: "⚠️" });
    }
    breakdown.distribution = distributionScore;
    score += distributionScore;

    // Clamp score between 0 and 100
    score = Math.max(0, Math.min(100, score));

    return { score, signals, breakdown };
  }, [marketData, breadthData, distributionDaysData]);

  // Determine exposure level and recommendation
  const getExposureLevel = (score) => {
    if (score >= 80) {
      return {
        level: "Aggressive",
        exposure: "80-100%",
        color: "success",
        description: "Strong uptrend with positive breadth",
        icon: <TrendingUp sx={{ color: theme.palette.success.main }} />,
      };
    } else if (score >= 60) {
      return {
        level: "Moderate-High",
        exposure: "60-80%",
        color: "info",
        description: "Generally positive conditions",
        icon: <TrendingUp sx={{ color: theme.palette.info.main }} />,
      };
    } else if (score >= 40) {
      return {
        level: "Moderate",
        exposure: "40-60%",
        color: "warning",
        description: "Mixed signals, selective positioning",
        icon: <TrendingFlat sx={{ color: theme.palette.warning.main }} />,
      };
    } else if (score >= 20) {
      return {
        level: "Conservative",
        exposure: "20-40%",
        color: "error",
        description: "Market weakness, raise cash",
        icon: <TrendingDown sx={{ color: theme.palette.error.main }} />,
      };
    } else {
      return {
        level: "Defensive",
        exposure: "0-20%",
        color: "error",
        description: "Significant weakness, maximum caution",
        icon: <TrendingDown sx={{ color: theme.palette.error.light }} />,
      };
    }
  };

  // Handle error/no data state
  if (exposureScore.error || exposureScore.score === null) {
    return (
      <Card
        sx={{
          background: theme.palette.background.paper,
          backdropFilter: "blur(10px)",
          border: `1px solid ${alpha(theme.palette.error.main, 0.2)}`,
          transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        }}
      >
        <CardContent>
          <Box sx={{ mb: 2 }}>
            <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
              Market Exposure
            </Typography>
            <Paper
              elevation={0}
              sx={{
                p: 2.5,
                background: alpha(theme.palette.error.main, 0.1),
                border: `2px solid ${theme.palette.error.main}`,
                borderRadius: 2,
              }}
            >
              <Typography variant="body2" color="error">
                ⚠️ Unable to calculate exposure: {exposureScore.error || "Market data unavailable"}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                Please ensure market data is loading correctly
              </Typography>
            </Paper>
          </Box>
        </CardContent>
      </Card>
    );
  }

  const exposureLevel = getExposureLevel(exposureScore.score);

  return (
    <Card
      sx={{
        background: theme.palette.background.paper,
        backdropFilter: "blur(10px)",
        border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
        transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
        "&:hover": {
          transform: "translateY(-2px)",
          boxShadow: theme.shadows[4],
          border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
        },
      }}
    >
      <CardContent>
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
            {exposureLevel.icon}
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Market Exposure
            </Typography>
            <Tooltip title="Recommended portfolio exposure to equities based on market conditions">
              <Info sx={{ fontSize: 18, color: "text.secondary" }} />
            </Tooltip>
          </Box>

          {/* Main Exposure Recommendation */}
          <Paper
            elevation={0}
            sx={{
              p: 2.5,
              background: alpha(theme.palette[exposureLevel.color].main, 0.1),
              border: `2px solid ${theme.palette[exposureLevel.color].main}`,
              borderRadius: 2,
              mb: 3,
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
              <Box>
                <Typography
                  variant="subtitle2"
                  color="text.secondary"
                  sx={{ fontWeight: 500 }}
                >
                  Current Exposure Level
                </Typography>
                <Typography
                  variant="h4"
                  sx={{
                    fontWeight: 700,
                    color: exposureLevel.color,
                  }}
                >
                  {exposureLevel.level}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  {exposureLevel.exposure} Recommended
                </Typography>
              </Box>
              <Box sx={{ flex: 1 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    Exposure Score
                  </Typography>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>
                    {Math.round(exposureScore.score)}/100
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={exposureScore.score}
                  sx={{
                    height: 8,
                    borderRadius: 1,
                    backgroundColor: alpha(theme.palette.text.primary, 0.1),
                    "& .MuiLinearProgress-bar": {
                      backgroundColor: theme.palette[exposureLevel.color].main,
                    },
                  }}
                />
              </Box>
            </Box>
            <Typography variant="body2" color="text.secondary">
              {exposureLevel.description}
            </Typography>
          </Paper>

          {/* Market Signals */}
          <Box>
            <Typography
              variant="subtitle2"
              sx={{ fontWeight: 600, mb: 1.5, color: "text.secondary" }}
            >
              Market Signals
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {exposureScore.signals.length > 0 ? (
                exposureScore.signals.map((signal, idx) => (
                  <Chip
                    key={idx}
                    icon={
                      signal.color === "success" ? (
                        <CheckCircle sx={{ fontSize: 16 }} />
                      ) : signal.color === "error" ? (
                        <Warning sx={{ fontSize: 16 }} />
                      ) : (
                        <Info sx={{ fontSize: 16 }} />
                      )
                    }
                    label={signal.label}
                    color={signal.color}
                    variant="outlined"
                    size="small"
                    sx={{
                      fontWeight: 500,
                      "& .MuiChip-icon": {
                        marginLeft: 1,
                        marginRight: -0.5,
                      },
                    }}
                  />
                ))
              ) : (
                <Typography variant="caption" color="text.secondary">
                  Analyzing market conditions...
                </Typography>
              )}
            </Stack>
          </Box>
        </Box>

        {/* Score Breakdown */}
        <Box sx={{ mt: 3, p: 1.5, backgroundColor: alpha(theme.palette.primary.main, 0.05), borderRadius: 1 }}>
          <Typography
            variant="subtitle2"
            sx={{ fontWeight: 600, mb: 1.5, color: "text.secondary" }}
          >
            Score Calculation
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={6} sm={4}>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Breadth
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 600,
                    color: exposureScore.breakdown?.breadth > 0 ? "success.main" :
                           exposureScore.breakdown?.breadth < 0 ? "error.main" : "text.primary"
                  }}
                >
                  {exposureScore.breakdown?.breadth !== null && exposureScore.breakdown?.breadth !== undefined
                    ? (() => {
                        const val = typeof exposureScore.breakdown.breadth === 'number' ? exposureScore.breakdown.breadth : parseFloat(exposureScore.breakdown.breadth) || 0;
                        return `${val >= 0 ? "+" : ""}${isNaN(val) ? '0.0' : val.toFixed(1)}`;
                      })()
                    : "N/A"}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Sentiment
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 600,
                    color: exposureScore.breakdown?.sentiment > 0 ? "success.main" :
                           exposureScore.breakdown?.sentiment < 0 ? "error.main" : "text.primary"
                  }}
                >
                  {exposureScore.breakdown?.sentiment !== null && exposureScore.breakdown?.sentiment !== undefined
                    ? (() => {
                        const val = typeof exposureScore.breakdown.sentiment === 'number' ? exposureScore.breakdown.sentiment : parseFloat(exposureScore.breakdown.sentiment) || 0;
                        return `${val >= 0 ? "+" : ""}${isNaN(val) ? '0.0' : val.toFixed(1)}`;
                      })()
                    : "N/A"}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={4}>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Distribution
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 600,
                    color: exposureScore.breakdown?.distribution < 0 ? "error.main" : "text.primary"
                  }}
                >
                  {exposureScore.breakdown?.distribution !== null && exposureScore.breakdown?.distribution !== undefined
                    ? (() => {
                        const val = typeof exposureScore.breakdown.distribution === 'number' ? exposureScore.breakdown.distribution : parseFloat(exposureScore.breakdown.distribution) || 0;
                        return `${val >= 0 ? "+" : ""}${isNaN(val) ? '0.0' : val.toFixed(1)}`;
                      })()
                    : "N/A"}
                </Typography>
              </Box>
            </Grid>
          </Grid>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
            Formula: 50 (base) + Breadth ± Sentiment ± Distribution
          </Typography>
        </Box>

        {/* Guidance Section */}
        <Box
          sx={{
            pt: 2,
            borderTop: `1px solid ${alpha(theme.palette.divider, 0.5)}`,
          }}
        >
          <Typography
            variant="subtitle2"
            sx={{ fontWeight: 600, mb: 1, color: "text.secondary" }}
          >
            Position Sizing Guidance
          </Typography>
          <Grid container spacing={1}>
            <Grid item xs={12} sm={6}>
              <Typography variant="caption" color="text.secondary" display="block">
                📈 If Bullish: Enter on strength
              </Typography>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Typography variant="caption" color="text.secondary" display="block">
                📉 If Bearish: Reduce exposure
              </Typography>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Typography variant="caption" color="text.secondary" display="block">
                ⚠️ If Mixed: Use trailing stops
              </Typography>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Typography variant="caption" color="text.secondary" display="block">
                💰 Scale in/out gradually
              </Typography>
            </Grid>
          </Grid>
        </Box>
      </CardContent>
    </Card>
  );
};

export default MarketExposure;
