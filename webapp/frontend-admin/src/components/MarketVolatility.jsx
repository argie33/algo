import { useState } from "react";
import {
  Box,
  Card,
  CardContent,
  Grid,
  LinearProgress,
  Typography,
  Alert,
  Paper,
} from "@mui/material";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp, TrendingDown } from "@mui/icons-material";
import { useTheme, alpha } from "@mui/material/styles";

const MarketVolatility = ({ data, isLoading, error }) => {
  const theme = useTheme();

  if (isLoading) {
    return <LinearProgress />;
  }

  if (error || !data?.data) {
    return (
      <Alert severity="error">
        Unable to load market volatility data. {error?.message}
      </Alert>
    );
  }

  const { market_volatility, avg_absolute_change } = data.data;

  // Handle case where required fields might be missing
  if (market_volatility === undefined || market_volatility === null) {
    return (
      <Alert severity="info">
        Volatility data not yet available.
      </Alert>
    );
  }

  // Determine volatility level
  let volatilityLevel = "Normal";
  let volatilityColor = theme.palette.info.main;

  if (market_volatility > 20) {
    volatilityLevel = "High";
    volatilityColor = theme.palette.error.main;
  } else if (market_volatility > 15) {
    volatilityLevel = "Elevated";
    volatilityColor = theme.palette.warning.main;
  } else if (market_volatility < 8) {
    volatilityLevel = "Low";
    volatilityColor = theme.palette.success.main;
  }

  const chartData = [
    { name: "Market Volatility", value: parseFloat(market_volatility) || 0 },
    { name: "Avg Daily Change", value: parseFloat(avg_absolute_change) || 0 },
  ];

  return (
    <Box>
      <Grid container spacing={3}>
        {/* Volatility Overview Card */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Volatility Overview
              </Typography>

              <Box
                sx={{
                  p: 3,
                  bgcolor: alpha(volatilityColor, 0.1),
                  borderRadius: 2,
                  border: `2px solid ${volatilityColor}`,
                  textAlign: "center",
                  mb: 2,
                }}
              >
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Current Volatility Level
                </Typography>
                <Typography
                  variant="h3"
                  sx={{
                    fontWeight: 700,
                    color: volatilityColor,
                    mb: 1,
                  }}
                >
                  {parseFloat(market_volatility).toFixed(2)}%
                </Typography>
                <Typography
                  variant="body1"
                  sx={{
                    fontWeight: 600,
                    color: volatilityColor,
                  }}
                >
                  {volatilityLevel}
                </Typography>
              </Box>

              <Paper elevation={0} sx={{ p: 2, bgcolor: "grey.50" }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                  {avg_absolute_change > 2 ? (
                    <TrendingUp sx={{ color: theme.palette.warning.main, fontSize: 32 }} />
                  ) : (
                    <TrendingDown sx={{ color: theme.palette.success.main, fontSize: 32 }} />
                  )}
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      Average Daily Change
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {parseFloat(avg_absolute_change).toFixed(3)}%
                    </Typography>
                  </Box>
                </Box>
              </Paper>
            </CardContent>
          </Card>
        </Grid>

        {/* Volatility Interpretation */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                What This Means
              </Typography>

              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                    📊 Market Volatility
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Measures the rate of price changes across all stocks. Higher volatility indicates
                    larger price swings and increased uncertainty.
                  </Typography>
                </Box>

                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                    📈 Average Daily Change
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Average magnitude of daily price changes. Shows typical daily movement range
                    across the market.
                  </Typography>
                </Box>

                <Box sx={{ p: 2, bgcolor: "grey.50", borderRadius: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                    ⚠️ Volatility Levels
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    • <strong>Low:</strong> &lt;8% - Calm market, low risk
                    <br />
                    • <strong>Normal:</strong> 8-15% - Typical conditions
                    <br />
                    • <strong>Elevated:</strong> 15-20% - Increased uncertainty
                    <br />
                    • <strong>High:</strong> &gt;20% - Significant volatility
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Volatility Chart */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                Volatility Metrics
              </Typography>
              <Box sx={{ height: 300, width: "100%" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip formatter={(value) => `${value.toFixed(3)}%`} />
                    <Bar dataKey="value" fill={theme.palette.primary.main} />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default MarketVolatility;
