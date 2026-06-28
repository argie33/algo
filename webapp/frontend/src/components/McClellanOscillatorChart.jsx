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
import { formatNumber } from "../utils/formatters";
import { getChartContainerStyle } from "../utils/chartContainer";

const McClellanOscillatorChart = ({ data, isLoading = false }) => {
  const theme = useTheme();

  if (isLoading) {
    return (
      <Card
        sx={{
          background: theme.palette.background.paper,
          backdropFilter: "blur(10px)",
          border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
        }}
      >
        <CardContent
          sx={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            minHeight: "300px",
          }}
        >
          <CircularProgress />
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card
        sx={{
          background: theme.palette.background.paper,
          backdropFilter: "blur(10px)",
          border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
        }}
      >
        <CardContent>
          <Typography color="textSecondary">
            No McClellan Oscillator data available
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const rawCurrentValue = data.current_value !== null && data.current_value !== undefined ? data.current_value : null;
  const currentValue =
    typeof rawCurrentValue === "number"
      ? rawCurrentValue
      : rawCurrentValue !== null && rawCurrentValue !== undefined ? parseFloat(rawCurrentValue) : null;
  const isBullish = currentValue !== null && currentValue > 0;
  const chartData = Array.isArray(data.recent_data)
    ? data.recent_data.slice(-20).map((item) => ({
        date: item.date
          ? new Date(item.date).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })
          : "—",
        value: item.advance_decline_line !== null && item.advance_decline_line !== undefined ? item.advance_decline_line : null,
      }))
    : [];

  return (
    <Card
      sx={{
        background: alpha(theme.palette.background.paper, 0.8),
        backdropFilter: "blur(10px)",
        border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
        transition: "all 0.3s ease",
        "&:hover": {
          boxShadow: theme.shadows[4],
        },
      }}
    >
      <CardContent>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            mb: 2,
          }}
        >
          <Box>
            <Typography
              variant="subtitle2"
              sx={{ opacity: 0.8, fontWeight: 500 }}
            >
              McClellan Oscillator (Breadth Momentum)
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 1 }}>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>
                {formatNumber(currentValue, 0)}
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

        <Box
          sx={{
            p: 1.5,
            bgcolor: alpha(theme.palette.info.main, 0.1),
            borderRadius: 1,
            border: `1px solid ${alpha(theme.palette.info.main, 0.2)}`,
            mb: 2,
          }}
        >
          <Typography
            variant="caption"
            sx={{ display: "block", fontWeight: 600 }}
          >
            Interpretation:
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.9, mt: 0.5 }}>
            {isBullish
              ? "Positive values indicate strong market breadth - advancing stocks are outpacing declines."
              : "Negative values suggest weakening breadth - declining stocks outpacing advances."}
          </Typography>
        </Box>

        {chartData.length > 0 && (
          <div style={{ ...getChartContainerStyle("compact"), marginTop: 16 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={chartData}
                margin={{ top: 20, right: 30, left: 60, bottom: 60 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke={alpha(theme.palette.divider, 0.5)}
                />
                <XAxis
                  dataKey="date"
                  stroke={theme.palette.text.secondary}
                  style={{ fontSize: "0.75rem" }}
                  tick={{ fill: theme.palette.text.secondary }}
                  angle={-45}
                  textAnchor="end"
                  height={60}
                  interval={Math.max(0, Math.floor(chartData.length / 8))}
                />
                <YAxis
                  stroke={theme.palette.text.secondary}
                  style={{ fontSize: "0.75rem" }}
                  width={50}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: alpha(
                      theme.palette.background.default,
                      0.95
                    ),
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: "4px",
                  }}
                  formatter={(value) => formatNumber(value, 0)}
                  labelStyle={{ color: theme.palette.text.primary }}
                  cursor={{ fill: alpha(theme.palette.primary.main, 0.1) }}
                />
                <ReferenceLine
                  y={0}
                  stroke={theme.palette.divider}
                  strokeDasharray="3 3"
                />
                <Bar
                  dataKey="value"
                  fill={
                    isBullish
                      ? theme.palette.success.main
                      : theme.palette.error.main
                  }
                  radius={[4, 4, 0, 0]}
                  opacity={0.7}
                  isAnimationActive={true}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {data.data_points && (
          <Typography
            variant="caption"
            sx={{ opacity: 0.6, display: "block", mt: 1 }}
          >
            Based on {data.data_points} trading days of advance/decline data
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

export default McClellanOscillatorChart;
