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
import { formatPercentageChange } from "../utils/formatters";
import { getChartContainerStyle } from "../utils/chartContainer";

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
  if (typeof market_volatility !== 'number' || isNaN(market_volatility)) {
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

  // Only include data that's actually available (no fake 0 values)
  const chartData = [];

  if (market_volatility !== null && market_volatility !== undefined) {
    chartData.push({
      name: "Market Volatility",
      value: parseFloat(market_volatility)
    });
  }

  if (avg_absolute_change !== null && avg_absolute_change !== undefined) {
    chartData.push({
      name: "Avg Daily Change",
      value: parseFloat(avg_absolute_change)
    });
  }

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
                  {formatPercentageChange(market_volatility, 2)}
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
                  {typeof avg_absolute_change === 'number' && avg_absolute_change > 2 ? (
                    <TrendingUp sx={{ color: theme.palette.warning.main, fontSize: 32 }} />
                  ) : (
                    <TrendingDown sx={{ color: theme.palette.success.main, fontSize: 32 }} />
                  )}
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      Average Daily Change
                    </Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatPercentageChange(avg_absolute_change, 3)}
                    </Typography>
                  </Box>
                </Box>
              </Paper>
            </CardContent>
          </Card>
        </Grid>

        {/* Volatility Chart */}
        {chartData.length > 0 && (
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                  Volatility Metrics
                </Typography>
                <div style={getChartContainerStyle('default')}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={chartData}
                      margin={{ top: 20, right: 30, left: 20, bottom: 50 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="name"
                        angle={-20}
                        textAnchor="end"
                        height={50}
                      />
                      <YAxis width={50} />
                      <Tooltip
                        formatter={(value) => formatPercentageChange(value, 3)}
                        contentStyle={{ backgroundColor: "rgba(0,0,0,0.85)", border: "1px solid #666", borderRadius: 4 }}
                        labelStyle={{ color: "#fff" }}
                      />
                      <Bar
                        dataKey="value"
                        fill={theme.palette.primary.main}
                        isAnimationActive={true}
                        radius={[4, 4, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    </Box>
  );
};

export default MarketVolatility;

