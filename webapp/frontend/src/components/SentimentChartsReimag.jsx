import {
  Box,
  Card,
  CardContent,
  Typography,
  alpha,
  useTheme,
} from "@mui/material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  Legend,
  ReferenceLine,
} from "recharts";

const SentimentChartsReimag = ({
  aaii_data,
  fearGreed_data,
  naaim_data,
}) => {
  const theme = useTheme();

  const chartColors = {
    bullish: "#10b981",
    neutral: "#f59e0b",
    bearish: "#ef4444",
    fearGreed: "#f43f5e",
    naaim: "#6366f1",
  };

  // Log data for debugging
  console.log("SentimentChartsReimag received:", {
    aaii_count: aaii_data?.length || 0,
    fearGreed_count: fearGreed_data?.length || 0,
    naaim_count: naaim_data?.length || 0,
  });

  if (!aaii_data?.length && !fearGreed_data?.length && !naaim_data?.length) {
    return (
      <Card>
        <CardContent>
          <Typography color="text.secondary" align="center" sx={{ py: 3 }}>
            No sentiment data available. Waiting for data load...
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box sx={{ width: "100%" }}>
      {/* AAII Line Chart */}
      {aaii_data && aaii_data.length > 0 && (
        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
              AAII Market Sentiment Trend
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
              Bullish (Green) vs Neutral (Amber) vs Bearish (Red). Each line represents the percentage of retail investors with that sentiment.
            </Typography>
            <Box sx={{ height: 350, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={aaii_data} margin={{ top: 15, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={alpha(theme.palette.divider, 0.2)} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: theme.palette.text.secondary }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} />
                  <ReferenceLine y={33} stroke={alpha(theme.palette.divider, 0.3)} strokeDasharray="4 4" label={{ value: "33%", fill: theme.palette.text.secondary, fontSize: 10 }} />
                  <ReferenceLine y={50} stroke={alpha(theme.palette.divider, 0.4)} strokeDasharray="4 4" label={{ value: "50%", fill: theme.palette.text.secondary, fontSize: 10 }} />
                  <ReferenceLine y={67} stroke={alpha(theme.palette.divider, 0.3)} strokeDasharray="4 4" label={{ value: "67%", fill: theme.palette.text.secondary, fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: alpha(theme.palette.background.paper, 0.95),
                      border: `1px solid ${theme.palette.divider}`,
                      borderRadius: 8,
                      boxShadow: theme.shadows[8],
                    }}
                    formatter={(value) => [`${value ? value.toFixed(1) : "N/A"}%`, ""]}
                    labelStyle={{ color: theme.palette.text.primary }}
                  />
                  <Legend wrapperStyle={{ paddingTop: 20 }} />
                  <Line
                    type="monotone"
                    dataKey="aaii_bullish"
                    name="Bullish %"
                    stroke={chartColors.bullish}
                    strokeWidth={3}
                    dot={{ r: 4, fill: chartColors.bullish }}
                    activeDot={{ r: 6 }}
                    isAnimationActive={true}
                  />
                  <Line
                    type="monotone"
                    dataKey="aaii_neutral"
                    name="Neutral %"
                    stroke={chartColors.neutral}
                    strokeWidth={3}
                    dot={{ r: 4, fill: chartColors.neutral }}
                    activeDot={{ r: 6 }}
                    isAnimationActive={true}
                  />
                  <Line
                    type="monotone"
                    dataKey="aaii_bearish"
                    name="Bearish %"
                    stroke={chartColors.bearish}
                    strokeWidth={3}
                    dot={{ r: 4, fill: chartColors.bearish }}
                    activeDot={{ r: 6 }}
                    isAnimationActive={true}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Fear & Greed Line Chart */}
      {fearGreed_data && fearGreed_data.length > 0 && (
        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
              Fear & Greed Index Trend
            </Typography>
            <Box sx={{ height: 350, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={fearGreed_data} margin={{ top: 15, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={alpha(theme.palette.divider, 0.2)} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: theme.palette.text.secondary }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} />
                  <ReferenceLine y={50} stroke={alpha(theme.palette.divider, 0.4)} strokeDasharray="5 5" label={{ value: "Neutral", fill: theme.palette.text.secondary, fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: alpha(theme.palette.background.paper, 0.95),
                      border: `1px solid ${theme.palette.divider}`,
                      borderRadius: 8,
                      boxShadow: theme.shadows[8],
                    }}
                    formatter={(value) => [`${value ? value.toFixed(1) : "N/A"}`, "Fear & Greed"]}
                    labelStyle={{ color: theme.palette.text.primary }}
                  />
                  <Legend wrapperStyle={{ paddingTop: 20 }} />
                  <Line
                    type="monotone"
                    dataKey="fear_greed"
                    name="Fear & Greed"
                    stroke={chartColors.fearGreed}
                    strokeWidth={3.5}
                    dot={{ r: 4, fill: chartColors.fearGreed }}
                    activeDot={{ r: 6 }}
                    isAnimationActive={true}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* NAAIM Line Chart */}
      {naaim_data && naaim_data.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
              NAAIM Manager Exposure Trend
            </Typography>
            <Box sx={{ height: 350, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={naaim_data} margin={{ top: 15, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={alpha(theme.palette.divider, 0.2)} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: theme.palette.text.secondary }} />
                  <YAxis domain={[-100, 100]} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} />
                  <ReferenceLine y={0} stroke={alpha(theme.palette.divider, 0.5)} strokeWidth={2} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: alpha(theme.palette.background.paper, 0.95),
                      border: `1px solid ${theme.palette.divider}`,
                      borderRadius: 8,
                      boxShadow: theme.shadows[8],
                    }}
                    formatter={(value) => [`${value ? value.toFixed(1) : "N/A"}%`, "NAAIM Exposure"]}
                    labelStyle={{ color: theme.palette.text.primary }}
                  />
                  <Legend wrapperStyle={{ paddingTop: 20 }} />
                  <Line
                    type="monotone"
                    dataKey="naaim"
                    name="NAAIM Exposure"
                    stroke={chartColors.naaim}
                    strokeWidth={3.5}
                    dot={{ r: 4, fill: chartColors.naaim }}
                    activeDot={{ r: 6 }}
                    isAnimationActive={true}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default SentimentChartsReimag;
