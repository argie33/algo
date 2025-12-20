import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  ButtonGroup,
  Card,
  CardContent,
  _Chip,
  CircularProgress,
  Typography,
  Divider,
  Paper,
} from "@mui/material";
import {
  ShowChart,
  TrendingUp,
  TrendingDown,
  Timeline,
  BarChart as BarChartIcon,
  _CandlestickChart,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  _Legend,
  _ComposedChart,
  Area,
  AreaChart,
  ReferenceLine,
  Cell,
} from "recharts";
import { getStockPrices } from "../services/api";
import { format } from "date-fns";
import { formatXAxisDate } from "../utils/dateFormatters";

const HistoricalPriceChart = ({ symbol = "AAPL", defaultPeriod = 30 }) => {
  const [period, setPeriod] = useState(defaultPeriod);
  const [timeframe, setTimeframe] = useState("daily");
  const [chartType, setChartType] = useState("line"); // line, area, bar, volume

  // Generate unique SVG gradient IDs for this component instance
  const { lineGradientId, colorCloseId } = useMemo(() => ({
    lineGradientId: `lineGradient-${Math.random().toString(36).substr(2, 9)}`,
    colorCloseId: `colorClose-${Math.random().toString(36).substr(2, 9)}`,
  }), []);

  const {
    data: priceData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["historical-prices", symbol, timeframe, period],
    queryFn: async () => {
      console.log(
        `Fetching ${timeframe} prices for ${symbol}, ${period} periods`
      );
      try {
        const result = await getStockPrices(symbol, timeframe, period);
        return result || { data: [] };
      } catch (err) {
        console.warn("Historical prices API failed, using fallback:", err.message);
        throw err;
      }
    },
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 2,
  });

  const formatPrice = (value) => {
    if (!value) return "N/A";
    return `$${value.toFixed(2)}`;
  };

  const formatDate = (dateString) => {
    if (!dateString) return "";
    try {
      return format(new Date(dateString), "MMM dd, yyyy");
    } catch {
      return dateString;
    }
  };

  const formatTooltipDate = (dateString) => {
    if (!dateString) return "";
    try {
      return format(new Date(dateString), "MMM dd, yyyy, h:mm a");
    } catch {
      return dateString;
    }
  };

  const chartData = priceData?.data || [];
  const latestPrice = chartData[0];
  const oldestPrice = chartData[(chartData?.length || 0) - 1];

  const priceChange =
    latestPrice && oldestPrice ? latestPrice.close - oldestPrice.close : 0;
  const priceChangePct =
    latestPrice && oldestPrice && oldestPrice.close
      ? (priceChange / oldestPrice.close) * 100
      : 0;

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && (payload?.length || 0)) {
      const data = payload[0].payload;
      return (
        <Box
          sx={{
            backgroundColor: "background.paper",
            border: 1,
            borderColor: "divider",
            borderRadius: 1,
            p: 2,
            boxShadow: 2,
          }}
        >
          <Typography variant="subtitle2" gutterBottom>
            {formatTooltipDate(label) || "No Date"}
          </Typography>
          <Typography variant="body2">
            <strong>Open:</strong> {formatPrice(data.open)}
          </Typography>
          <Typography variant="body2">
            <strong>High:</strong> {formatPrice(data.high)}
          </Typography>
          <Typography variant="body2">
            <strong>Low:</strong> {formatPrice(data.low)}
          </Typography>
          <Typography variant="body2">
            <strong>Close:</strong> {formatPrice(data.close)}
          </Typography>
          <Typography variant="body2">
            <strong>Volume:</strong> {data.volume?.toLocaleString() || "N/A"}
          </Typography>
        </Box>
      );
    }
    return <Box />;
  };

  return (
    <Card sx={{ height: "100%", boxShadow: 3 }}>
      <CardContent sx={{ p: 3 }}>
        {/* Header */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 3,
            pb: 2,
            borderBottom: 2,
            borderColor: "divider",
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <ShowChart sx={{ color: "primary.main", fontSize: 32 }} />
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {symbol} Price Chart
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {timeframe.charAt(0).toUpperCase() + timeframe.slice(1)} •{" "}
                {period} periods
              </Typography>
            </Box>
          </Box>
          <Button
            variant="contained"
            size="medium"
            onClick={() => refetch()}
            disabled={isLoading}
            startIcon={<Timeline />}
            sx={{ fontWeight: 600 }}
          >
            Refresh
          </Button>
        </Box>

        {/* Price Summary - More Prominent */}
        {latestPrice && oldestPrice && (
          <Paper
            elevation={2}
            sx={{
              p: 2.5,
              mb: 3,
              background: "linear-gradient(135deg, rgba(25, 118, 210, 0.08), rgba(67, 160, 71, 0.08))",
              borderRadius: 2,
            }}
          >
            <Box sx={{ display: "flex", gap: 3, flexWrap: "wrap", mb: 2 }}>
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                  Current Price
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: "primary.main" }}>
                  {formatPrice(latestPrice.close)}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                  Period Change
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  {priceChange >= 0 ? (
                    <TrendingUp sx={{ color: "success.main", fontSize: 20 }} />
                  ) : (
                    <TrendingDown sx={{ color: "error.main", fontSize: 20 }} />
                  )}
                  <Typography
                    variant="h6"
                    sx={{
                      fontWeight: 700,
                      color: priceChange >= 0 ? "success.main" : "error.main",
                    }}
                  >
                    {priceChange >= 0 ? "+" : ""}{formatPrice(priceChange)} ({priceChangePct.toFixed(2)}%)
                  </Typography>
                </Box>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                  Latest Volume
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {latestPrice.volume?.toLocaleString() || "N/A"}
                </Typography>
              </Box>
            </Box>
          </Paper>
        )}

        {/* Controls - Larger and More Visible */}
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1.5, color: "text.secondary" }}>
            Timeframe
          </Typography>
          <ButtonGroup variant="outlined" sx={{ mb: 2.5 }} fullWidth>
            <Button
              onClick={() => setTimeframe("daily")}
              variant={timeframe === "daily" ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              Daily
            </Button>
            <Button
              onClick={() => setTimeframe("weekly")}
              variant={timeframe === "weekly" ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              Weekly
            </Button>
            <Button
              onClick={() => setTimeframe("monthly")}
              variant={timeframe === "monthly" ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              Monthly
            </Button>
          </ButtonGroup>

          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1.5, color: "text.secondary" }}>
            Period
          </Typography>
          <ButtonGroup variant="outlined" sx={{ mb: 2.5 }} fullWidth>
            <Button
              onClick={() => setPeriod(30)}
              variant={period === 30 ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              30 Days
            </Button>
            <Button
              onClick={() => setPeriod(90)}
              variant={period === 90 ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              90 Days
            </Button>
            <Button
              onClick={() => setPeriod(252)}
              variant={period === 252 ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              1 Year
            </Button>
          </ButtonGroup>

          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1.5, color: "text.secondary" }}>
            Chart Type
          </Typography>
          <ButtonGroup variant="outlined" fullWidth>
            <Button
              onClick={() => setChartType("line")}
              variant={chartType === "line" ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              Line
            </Button>
            <Button
              onClick={() => setChartType("area")}
              variant={chartType === "area" ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              Area
            </Button>
            <Button
              onClick={() => setChartType("bar")}
              variant={chartType === "bar" ? "contained" : "outlined"}
              size="medium"
              startIcon={<BarChartIcon />}
              sx={{ fontWeight: 600 }}
            >
              Bars
            </Button>
            <Button
              onClick={() => setChartType("volume")}
              variant={chartType === "volume" ? "contained" : "outlined"}
              size="medium"
              sx={{ fontWeight: 600 }}
            >
              Volume
            </Button>
          </ButtonGroup>
        </Box>

        <Divider sx={{ my: 2 }} />

        {/* Loading State */}
        {isLoading && (
          <Box
            sx={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              height: 300,
            }}
          >
            <CircularProgress />
          </Box>
        )}

        {/* Error State */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            <Typography variant="subtitle2">
              Failed to load price data
            </Typography>
            <Typography variant="body2">
              {error.message || "Unknown error occurred"}
            </Typography>
          </Alert>
        )}

        {/* Chart Section - Large and Prominent */}
        {!isLoading && !error && chartData.length > 0 && (
          <Box>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, color: "text.secondary" }}>
              {chartType === "line" && "Price Line Chart"}
              {chartType === "area" && "Price Area Chart"}
              {chartType === "bar" && "Daily Price Bars"}
              {chartType === "volume" && "Trading Volume"}
            </Typography>

            <ResponsiveContainer
              width="100%"
              height={500}
              data-testid="responsive-container"
            >
              {chartType === "line" && (
                <LineChart
                  data={[...chartData].reverse()}
                  data-testid="line-chart"
                  margin={{ top: 20, right: 30, left: 0, bottom: 10 }}
                >
                  <defs>
                    <linearGradient id={lineGradientId} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#1976d2" stopOpacity={0.4}/>
                      <stop offset="100%" stopColor="#1976d2" stopOpacity={0.05}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="2 2"
                    stroke="rgba(0,0,0,0.08)"
                    data-testid="cartesian-grid"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 12, fill: "#888" }}
                    interval={Math.floor([...chartData].reverse().length / 5)}
                    data-testid="x-axis"
                    data-key="date"
                    tickFormatter={formatXAxisDate}
                  />
                  <YAxis
                    tick={{ fontSize: 12, fill: "#888" }}
                    domain={["auto", "auto"]}
                    data-testid="y-axis"
                    label={{ value: "Price ($)", angle: -90, position: "insideLeft", offset: 10 }}
                    width={50}
                  />
                  {/* Reference lines for key price levels */}
                  <ReferenceLine
                    y={Math.max(...chartData.map(d => d.close))}
                    stroke="#43a047"
                    strokeDasharray="5 5"
                    opacity={0.3}
                    label={{ value: "High", position: "right", fill: "#43a047", fontSize: 11 }}
                  />
                  <ReferenceLine
                    y={Math.min(...chartData.map(d => d.close))}
                    stroke="#e53935"
                    strokeDasharray="5 5"
                    opacity={0.3}
                    label={{ value: "Low", position: "right", fill: "#e53935", fontSize: 11 }}
                  />
                  <Tooltip
                    content={<CustomTooltip />}
                    data-testid="chart-tooltip"
                    cursor={{ stroke: "#1976d2", strokeWidth: 3, opacity: 0.7 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="close"
                    stroke="#1976d2"
                    strokeWidth={4}
                    dot={(props) => {
                      const { cx, cy, payload } = props;
                      const reversedData = [...chartData].reverse();
                      const index = reversedData.findIndex(d => d.date === payload.date);
                      const isUp = index === 0 || reversedData[index].close >= reversedData[index - 1].close;
                      return (
                        <circle
                          cx={cx}
                          cy={cy}
                          r={5}
                          fill={isUp ? "#43a047" : "#e53935"}
                          stroke="white"
                          strokeWidth={2}
                          opacity={0.9}
                        />
                      );
                    }}
                    activeDot={{ r: 7, fill: "#1976d2", strokeWidth: 2 }}
                    data-testid="chart-line"
                    isAnimationActive={true}
                  />
                </LineChart>
              )}

              {chartType === "area" && (
                <AreaChart
                  data={[...chartData].reverse()}
                  margin={{ top: 20, right: 30, left: 0, bottom: 10 }}
                >
                  <defs>
                    <linearGradient id={colorCloseId} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#1976d2" stopOpacity={0.6}/>
                      <stop offset="100%" stopColor="#1976d2" stopOpacity={0.05}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 2" stroke="rgba(0,0,0,0.08)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 12, fill: "#888" }} interval={Math.floor([...chartData].reverse().length / 5)} tickFormatter={formatXAxisDate} />
                  <YAxis tick={{ fontSize: 12, fill: "#888" }} label={{ value: "Price ($)", angle: -90, position: "insideLeft", offset: 10 }} width={50} />
                  <ReferenceLine
                    y={Math.max(...chartData.map(d => d.close))}
                    stroke="#43a047"
                    strokeDasharray="5 5"
                    opacity={0.3}
                    label={{ value: "High", position: "right", fill: "#43a047", fontSize: 11 }}
                  />
                  <ReferenceLine
                    y={Math.min(...chartData.map(d => d.close))}
                    stroke="#e53935"
                    strokeDasharray="5 5"
                    opacity={0.3}
                    label={{ value: "Low", position: "right", fill: "#e53935", fontSize: 11 }}
                  />
                  <Tooltip content={<CustomTooltip />} cursor={{ stroke: "#1976d2", strokeWidth: 3, opacity: 0.7 }} />
                  <Area
                    type="monotone"
                    dataKey="close"
                    stroke="#1976d2"
                    strokeWidth={4}
                    fillOpacity={1}
                    fill={`url(#${colorCloseId})`}
                    isAnimationActive={true}
                  />
                </AreaChart>
              )}

              {chartType === "bar" && (
                <BarChart
                  data={[...chartData].reverse()}
                  margin={{ top: 20, right: 30, left: 0, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="2 2" stroke="rgba(0,0,0,0.08)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 12, fill: "#888" }} interval={Math.floor([...chartData].reverse().length / 5)} tickFormatter={formatXAxisDate} />
                  <YAxis tick={{ fontSize: 12, fill: "#888" }} label={{ value: "Price ($)", angle: -90, position: "insideLeft", offset: 10 }} width={50} />
                  <ReferenceLine
                    y={Math.max(...chartData.map(d => d.close))}
                    stroke="#43a047"
                    strokeDasharray="5 5"
                    opacity={0.3}
                    label={{ value: "High", position: "right", fill: "#43a047", fontSize: 11 }}
                  />
                  <ReferenceLine
                    y={Math.min(...chartData.map(d => d.close))}
                    stroke="#e53935"
                    strokeDasharray="5 5"
                    opacity={0.3}
                    label={{ value: "Low", position: "right", fill: "#e53935", fontSize: 11 }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="close" fill="#1976d2" radius={[6, 6, 0, 0]}>
                    {[...chartData].reverse().map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.close >= (chartData[chartData.length - 1]?.close || 0) ? "#43a047" : "#e53935"}
                        opacity={0.85}
                      />
                    ))}
                  </Bar>
                </BarChart>
              )}

              {chartType === "volume" && (
                <BarChart
                  data={[...chartData].reverse()}
                  margin={{ top: 20, right: 30, left: 0, bottom: 10 }}
                >
                  <CartesianGrid strokeDasharray="2 2" stroke="rgba(0,0,0,0.08)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 12, fill: "#888" }} interval={Math.floor([...chartData].reverse().length / 5)} tickFormatter={formatXAxisDate} />
                  <YAxis tick={{ fontSize: 12, fill: "#888" }} label={{ value: "Volume", angle: -90, position: "insideLeft", offset: 10 }} width={50} />
                  <ReferenceLine
                    y={Math.max(...chartData.map(d => d.volume || 0))}
                    stroke="#ff9800"
                    strokeDasharray="5 5"
                    opacity={0.3}
                    label={{ value: "Peak", position: "right", fill: "#ff9800", fontSize: 11 }}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        return (
                          <Box sx={{ backgroundColor: "background.paper", border: 1, borderColor: "divider", borderRadius: 1, p: 1.5 }}>
                            <Typography variant="body2"><strong>Date:</strong> {payload[0].payload.date}</Typography>
                            <Typography variant="body2"><strong>Volume:</strong> {payload[0].value?.toLocaleString()}</Typography>
                          </Box>
                        );
                      }
                      return null;
                    }}
                  />
                  <Bar dataKey="volume" fill="#ff9800" radius={[4, 4, 0, 0]} opacity={0.85} />
                </BarChart>
              )}
            </ResponsiveContainer>
          </Box>
        )}

        {/* No Data State */}
        {!isLoading && !error && (chartData?.length || 0) === 0 && (
          <Alert severity="info">
            <Typography variant="subtitle2">No price data available</Typography>
            <Typography variant="body2">
              The price data for {symbol} ({timeframe}) is not yet loaded. The
              price loaders need to populate the database tables.
            </Typography>
          </Alert>
        )}

        {/* Data Summary */}
        {chartData.length > 0 && (
          <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
            <Typography variant="caption" color="text.secondary">
              Showing {chartData?.length || 0} {timeframe} data points for{" "}
              {symbol}
              {latestPrice && ` • Latest: ${formatDate(latestPrice.date)}`}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default HistoricalPriceChart;
