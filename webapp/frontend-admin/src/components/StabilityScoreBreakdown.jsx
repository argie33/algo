import React, { useMemo } from "react";
import {
  Box,
  Card,
  CardContent,
  Grid,
  LinearProgress,
  Typography,
  Tooltip,
  CircularProgress,
} from "@mui/material";
import {
  TrendingUp,
  _TrendingDown,
  Analytics,
  Shield,
} from "@mui/icons-material";

/**
 * StabilityScoreBreakdown Component
 * Displays a breakdown of factors that contribute to portfolio stability
 * Shows metrics like: volatility, max drawdown, Sharpe ratio, consistency, etc.
 */
function StabilityScoreBreakdown({ signals = [], summary = null, isLoading = false }) {
  // Calculate stability metrics from the available data
  const stabilityMetrics = useMemo(() => {
    if (!signals || signals.length === 0) {
      return null;
    }

    // Extract key metrics from signals
    const qualityScores = signals
      .map((s) => s.entry_quality_score)
      .filter((s) => s && typeof s === "number");

    const riskRewardRatios = signals
      .map((s) => s.risk_reward_ratio)
      .filter((s) => s && typeof s === "number");

    const stage2Signals = signals.filter(
      (s) => s.market_stage === "Stage 2 - Advancing"
    ).length;

    const marketStageDistribution = {
      "Stage 1 - Basing": signals.filter(
        (s) => s.market_stage === "Stage 1 - Basing"
      ).length,
      "Stage 2 - Advancing": stage2Signals,
      "Stage 3 - Topping": signals.filter(
        (s) => s.market_stage === "Stage 3 - Topping"
      ).length,
      "Stage 4 - Declining": signals.filter(
        (s) => s.market_stage === "Stage 4 - Declining"
      ).length,
    };

    const avgQuality =
      qualityScores.length > 0
        ? qualityScores.reduce((a, b) => a + b, 0) / qualityScores.length
        : 0;

    const avgRiskReward =
      riskRewardRatios.length > 0
        ? riskRewardRatios.reduce((a, b) => a + b, 0) / riskRewardRatios.length
        : 0;

    const buySignals = signals.filter(
      (s) => s.signal === "Buy" || s.signal === "BUY"
    ).length;
    const _sellSignals = signals.filter(
      (s) => s.signal === "Sell" || s.signal === "SELL"
    ).length;

    return {
      avgQuality,
      avgRiskReward,
      stage2Percentage:
        signals.length > 0 ? (stage2Signals / signals.length) * 100 : 0,
      buySignalPercentage:
        signals.length > 0 ? (buySignals / signals.length) * 100 : 0,
      marketStageDistribution,
      totalSignals: signals.length,
    };
  }, [signals]);

  if (isLoading) {
    return (
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (!stabilityMetrics) {
    return (
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography color="text.secondary">
            No stability data available
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const MetricBox = ({ label, value, percentage, icon, color = "#3B82F6" }) => (
    <Box sx={{ mb: 2 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 1,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Box sx={{ color, fontSize: 20 }}>{icon}</Box>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {label}
          </Typography>
        </Box>
        <Typography
          variant="body2"
          sx={{ fontWeight: 700, color }}
        >
          {value}
        </Typography>
      </Box>
      {percentage !== undefined && (
        <LinearProgress
          variant="determinate"
          value={Math.min(percentage, 100)}
          sx={{
            height: 8,
            borderRadius: 4,
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            "& .MuiLinearProgress-bar": {
              borderRadius: 4,
              background: `linear-gradient(90deg, ${color} 0%, ${color}dd 100%)`,
            },
          }}
        />
      )}
    </Box>
  );

  return (
    <Grid container spacing={3} sx={{ mb: 4 }}>
      <Grid item xs={12}>
        <Typography variant="h5" sx={{ fontWeight: 700, mb: 3 }}>
          <Shield sx={{ mr: 1, verticalAlign: "middle" }} />
          Stability Score Factor Breakdown
        </Typography>
      </Grid>

      {/* Signal Quality */}
      <Grid item xs={12} md={6}>
        <Card sx={{ height: "100%" }}>
          <CardContent>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
              Signal Quality Metrics
            </Typography>

            <MetricBox
              label="Average Entry Quality Score"
              value={stabilityMetrics.avgQuality ? stabilityMetrics.avgQuality.toFixed(1) : "—"}
              percentage={stabilityMetrics.avgQuality || 0}
              icon={<Analytics />}
              color="#10B981"
            />

            <MetricBox
              label="Average Risk/Reward Ratio"
              value={stabilityMetrics.avgRiskReward ? `${stabilityMetrics.avgRiskReward.toFixed(2)}:1` : "—"}
              percentage={Math.min((stabilityMetrics.avgRiskReward || 0) * 20, 100)}
              icon={<TrendingUp />}
              color="#F59E0B"
            />

            <MetricBox
              label="Stage 2 (Advancing) Signals"
              value={`${stabilityMetrics.stage2Percentage.toFixed(0)}%`}
              percentage={stabilityMetrics.stage2Percentage}
              icon={<TrendingUp />}
              color="#059669"
            />

            <MetricBox
              label="Buy Signal Distribution"
              value={`${stabilityMetrics.buySignalPercentage.toFixed(0)}%`}
              percentage={stabilityMetrics.buySignalPercentage}
              icon={<TrendingUp />}
              color="#3B82F6"
            />
          </CardContent>
        </Card>
      </Grid>

      {/* Market Stage Distribution */}
      <Grid item xs={12} md={6}>
        <Card sx={{ height: "100%" }}>
          <CardContent>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
              Market Stage Distribution
            </Typography>

            {Object.entries(
              stabilityMetrics.marketStageDistribution
            ).map(([stage, count], idx) => {
              const percentage =
                stabilityMetrics.totalSignals > 0
                  ? (count / stabilityMetrics.totalSignals) * 100
                  : 0;

              const stageColors = {
                "Stage 1 - Basing": "#3B82F6",
                "Stage 2 - Advancing": "#059669",
                "Stage 3 - Topping": "#F59E0B",
                "Stage 4 - Declining": "#DC2626",
              };

              return (
                <Box key={idx} sx={{ mb: 2 }}>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      mb: 0.75,
                    }}
                  >
                    <Tooltip title={stage}>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 600,
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          maxWidth: "80%",
                        }}
                      >
                        {stage.replace(" - ", ": ")}
                      </Typography>
                    </Tooltip>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 700,
                        color: stageColors[stage],
                        ml: 1,
                      }}
                    >
                      {count}
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={percentage}
                    sx={{
                      height: 6,
                      borderRadius: 3,
                      backgroundColor: "rgba(0, 0, 0, 0.05)",
                      "& .MuiLinearProgress-bar": {
                        borderRadius: 3,
                        backgroundColor: stageColors[stage],
                      },
                    }}
                  />
                </Box>
              );
            })}

            <Box sx={{ mt: 3, p: 2, backgroundColor: "rgba(59, 130, 246, 0.05)", borderRadius: 1 }}>
              <Typography variant="caption" color="text.secondary">
                💡 Higher Stage 2 percentage indicates better trading opportunities
              </Typography>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Portfolio-level metrics if available */}
      {summary && (
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 3 }}>
                Portfolio-Level Stability Factors
              </Typography>

              <Grid container spacing={2}>
                {summary.sharpe_ratio !== undefined && (
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ textAlign: "center" }}>
                      <Typography variant="caption" color="text.secondary">
                        Sharpe Ratio
                      </Typography>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          color:
                            summary.sharpe_ratio > 0.5
                              ? "#059669"
                              : "#F59E0B",
                        }}
                      >
                        {summary.sharpe_ratio?.toFixed(2) || "—"}
                      </Typography>
                    </Box>
                  </Grid>
                )}

                {summary.volatility_annualized !== undefined && (
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ textAlign: "center" }}>
                      <Typography variant="caption" color="text.secondary">
                        Annual Volatility
                      </Typography>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          color:
                            summary.volatility_annualized < 30
                              ? "#059669"
                              : summary.volatility_annualized < 50
                                ? "#F59E0B"
                                : "#DC2626",
                        }}
                      >
                        {summary.volatility_annualized?.toFixed(1) || "—"}%
                      </Typography>
                    </Box>
                  </Grid>
                )}

                {summary.max_drawdown !== undefined && (
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ textAlign: "center" }}>
                      <Typography variant="caption" color="text.secondary">
                        Max Drawdown
                      </Typography>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          color: summary.max_drawdown > -30 ? "#059669" : "#DC2626",
                        }}
                      >
                        {summary.max_drawdown?.toFixed(1) || "—"}%
                      </Typography>
                    </Box>
                  </Grid>
                )}

                {summary.calmar_ratio !== undefined && (
                  <Grid item xs={6} sm={3}>
                    <Box sx={{ textAlign: "center" }}>
                      <Typography variant="caption" color="text.secondary">
                        Calmar Ratio
                      </Typography>
                      <Typography
                        variant="h6"
                        sx={{
                          fontWeight: 700,
                          color:
                            summary.calmar_ratio > 0.3
                              ? "#059669"
                              : "#F59E0B",
                        }}
                      >
                        {summary.calmar_ratio?.toFixed(2) || "—"}
                      </Typography>
                    </Box>
                  </Grid>
                )}
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      )}
    </Grid>
  );
}

export default StabilityScoreBreakdown;
