import {
  Card,
  CardContent,
  Box,
  Typography,
  CircularProgress,
  useTheme,
  alpha,
  Chip,
  Grid,
} from "@mui/material";
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { TrendingUp, TrendingDown, Info } from "@mui/icons-material";

const SentimentDivergenceChart = ({ data, isLoading = false }) => {
  const theme = useTheme();

  if (isLoading) {
    return (
      <Card sx={{
        background: theme.palette.background.paper,
        backdropFilter: "blur(10px)",
        border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
      }}>
        <CardContent sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "300px" }}>
          <CircularProgress />
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card sx={{
        background: theme.palette.background.paper,
        backdropFilter: "blur(10px)",
        border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
      }}>
        <CardContent>
          <Typography color="textSecondary">No sentiment divergence data available</Typography>
        </CardContent>
      </Card>
    );
  }

  const currentData = data.current || {};
  const historicalData = data.historical || [];
  const divergence = currentData.divergence || 0;
  const retailBullish = currentData.retail_bullish || 0;
  const professionalBullish = currentData.professional_bullish || 0;

  // Determine sentiment signal
  const getSignalColor = (signal) => {
    if (!signal) return theme.palette.info.main;
    if (signal.includes("Retail Overly")) return theme.palette.error.main;
    if (signal.includes("Professionals Overly")) return theme.palette.success.main;
    if (signal.includes("More Bullish")) return theme.palette.warning.main;
    return theme.palette.info.main;
  };

  const chartData = historicalData.slice(-20).map(item => ({
    date: new Date(item.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    retail: parseFloat(item.retail_bullish) || 0,
    professional: parseFloat(item.professional_bullish) || 0,
  }));

  const isDivergent = Math.abs(divergence) > 5;

  return (
    <Card
      sx={{
        background: alpha(theme.palette.background.paper, 0.8),
        backdropFilter: "blur(10px)",
        border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
        transition: "all 0.3s ease",
        "&:hover": {
          boxShadow: theme.shadows[4],
        }
      }}
    >
      <CardContent>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
          <Box>
            <Typography variant="subtitle2" sx={{ opacity: 0.8, fontWeight: 500 }}>
              Smart Money vs Retail Sentiment
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.7, mt: 0.5 }}>
              Professional Managers (NAAIM) vs Retail Investors (AAII)
            </Typography>
          </Box>
          {isDivergent && (
            <Chip
              icon={<TrendingUp />}
              label="DIVERGENCE"
              color="warning"
              size="small"
              variant="outlined"
            />
          )}
        </Box>

        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} sm={6}>
            <Box sx={{
              p: 1.5,
              bgcolor: alpha(theme.palette.primary.main, 0.1),
              borderRadius: 1,
              border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`
            }}>
              <Typography variant="caption" sx={{ opacity: 0.7, fontWeight: 600 }}>
                Professional Managers (NAAIM)
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700, mt: 0.5 }}>
                {professionalBullish.toFixed(1)}%
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.8, mt: 0.5 }}>
                Bullish
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Box sx={{
              p: 1.5,
              bgcolor: alpha(theme.palette.success.main, 0.1),
              borderRadius: 1,
              border: `1px solid ${alpha(theme.palette.success.main, 0.2)}`
            }}>
              <Typography variant="caption" sx={{ opacity: 0.7, fontWeight: 600 }}>
                Retail Investors (AAII)
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700, mt: 0.5 }}>
                {retailBullish.toFixed(1)}%
              </Typography>
              <Typography variant="body2" sx={{ opacity: 0.8, mt: 0.5 }}>
                Bullish
              </Typography>
            </Box>
          </Grid>
        </Grid>

        {currentData.signal && (
          <Box sx={{
            p: 1.5,
            bgcolor: alpha(getSignalColor(currentData.signal), 0.1),
            borderRadius: 1,
            border: `1px solid ${alpha(getSignalColor(currentData.signal), 0.3)}`,
            mb: 2,
          }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
              {divergence > 0 ? (
                <TrendingUp sx={{ color: getSignalColor(currentData.signal), fontSize: "1.2rem" }} />
              ) : (
                <TrendingDown sx={{ color: getSignalColor(currentData.signal), fontSize: "1.2rem" }} />
              )}
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {currentData.signal}
              </Typography>
            </Box>
            <Typography variant="caption" sx={{ opacity: 0.8 }}>
              Divergence: {Math.abs(divergence).toFixed(1)}% ({divergence > 0 ? "Retail more bullish" : "Professionals more bullish"})
            </Typography>
          </Box>
        )}

        {chartData.length > 0 && (
          <Box sx={{ width: "100%", height: 250, mt: 2 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={alpha(theme.palette.divider, 0.5)} />
                <XAxis
                  dataKey="date"
                  stroke={theme.palette.text.secondary}
                  style={{ fontSize: "0.75rem" }}
                  tick={{ fill: theme.palette.text.secondary }}
                />
                <YAxis
                  stroke={theme.palette.text.secondary}
                  style={{ fontSize: "0.75rem" }}
                  domain={[0, 100]}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: alpha(theme.palette.background.default, 0.95),
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: "4px",
                  }}
                  formatter={(value) => value.toFixed(1)}
                  labelStyle={{ color: theme.palette.text.primary }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="professional"
                  stroke={theme.palette.primary.main}
                  dot={false}
                  strokeWidth={2}
                  name="Professional (NAAIM)"
                />
                <Line
                  type="monotone"
                  dataKey="retail"
                  stroke={theme.palette.success.main}
                  dot={false}
                  strokeWidth={2}
                  name="Retail (AAII)"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </Box>
        )}

        <Box sx={{
          p: 1,
          bgcolor: alpha(theme.palette.info.main, 0.05),
          borderRadius: 1,
          border: `1px solid ${alpha(theme.palette.info.main, 0.2)}`,
          mt: 2,
          display: "flex",
          gap: 1,
        }}>
          <Info sx={{ fontSize: "1rem", opacity: 0.7, flexShrink: 0, mt: 0.25 }} />
          <Typography variant="caption" sx={{ opacity: 0.8 }}>
            Large divergences between smart money and retail can signal potential reversals. When retail is overly bullish, smart money reduces exposure.
          </Typography>
        </Box>

        {currentData.date && (
          <Typography variant="caption" sx={{ opacity: 0.6, display: "block", mt: 1 }}>
            As of {new Date(currentData.date).toLocaleDateString()}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default SentimentDivergenceChart;
