import {
  Card,
  CardContent,
  Box,
  Typography,
  CircularProgress,
  useTheme,
  alpha,
  Chip,
} from "@mui/material";
import {
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { TrendingUp, TrendingDown } from "@mui/icons-material";

const McClellanOscillatorChart = ({ data, isLoading = false }) => {
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
          <Typography color="textSecondary">No McClellan Oscillator data available</Typography>
        </CardContent>
      </Card>
    );
  }

  const currentValue = data.current_value || 0;
  const isBullish = currentValue > 0;
  const chartData = data.recent_data ? data.recent_data.slice(-20).map(item => ({
    date: new Date(item.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    value: item.advance_decline_line || 0,
  })) : [];

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
              McClellan Oscillator (Breadth Momentum)
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1 }}>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>
                {currentValue.toFixed(0)}
              </Typography>
              {isBullish ? (
                <Chip
                  icon={<TrendingUp />}
                  label="Bullish"
                  color="success"
                  size="small"
                  variant="outlined"
                />
              ) : (
                <Chip
                  icon={<TrendingDown />}
                  label="Bearish"
                  color="error"
                  size="small"
                  variant="outlined"
                />
              )}
            </Box>
          </Box>
        </Box>

        <Box sx={{
          p: 1.5,
          bgcolor: alpha(theme.palette.info.main, 0.1),
          borderRadius: 1,
          border: `1px solid ${alpha(theme.palette.info.main, 0.2)}`,
          mb: 2,
        }}>
          <Typography variant="caption" sx={{ display: "block", fontWeight: 600 }}>
            Interpretation:
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.9, mt: 0.5 }}>
            {isBullish
              ? "Positive values indicate strong market breadth - advancing stocks are outpacing declines."
              : "Negative values suggest weakening breadth - declining stocks outpacing advances."}
          </Typography>
        </Box>

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
                <YAxis stroke={theme.palette.text.secondary} style={{ fontSize: "0.75rem" }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: alpha(theme.palette.background.default, 0.95),
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: "4px",
                  }}
                  formatter={(value) => value.toFixed(0)}
                  labelStyle={{ color: theme.palette.text.primary }}
                />
                <ReferenceLine
                  y={0}
                  stroke={theme.palette.divider}
                  strokeDasharray="3 3"
                />
                <Bar
                  dataKey="value"
                  fill={isBullish ? theme.palette.success.main : theme.palette.error.main}
                  radius={[4, 4, 0, 0]}
                  opacity={0.7}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </Box>
        )}

        {data.data_points && (
          <Typography variant="caption" sx={{ opacity: 0.6, display: "block", mt: 1 }}>
            Based on {data.data_points} trading days of advance/decline data
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default McClellanOscillatorChart;
