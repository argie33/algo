import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  ButtonGroup,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Typography,
} from "@mui/material";
import {
  ShowChart,
  TrendingUp,
  TrendingDown,
  Timeline,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { getStockPrices } from "../services/api";
import { format } from "date-fns";

const HistoricalPriceChart = ({ symbol = "AAPL", defaultPeriod = 30 }) => {
  const [period, setPeriod] = useState(defaultPeriod);
  const [timeframe, setTimeframe] = useState("daily");

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
      return await getStockPrices(symbol, timeframe, period);
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
    <Card sx={{ height: "100%" }}>
      <CardContent>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 2,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <ShowChart sx={{ color: "primary.main" }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Historical Prices - {symbol}
            </Typography>
          </Box>
          <Button
            variant="outlined"
            size="small"
            onClick={() => refetch()}
            disabled={isLoading}
            startIcon={<Timeline />}
          >
            Refresh
          </Button>
        </Box>

        {/* Controls */}
        <Box sx={{ display: "flex", gap: 2, mb: 2, flexWrap: "wrap" }}>
          <ButtonGroup size="small" variant="outlined">
            <Button
              onClick={() => setTimeframe("daily")}
              variant={timeframe === "daily" ? "contained" : "outlined"}
            >
              Daily
            </Button>
            <Button
              onClick={() => setTimeframe("weekly")}
              variant={timeframe === "weekly" ? "contained" : "outlined"}
            >
              Weekly
            </Button>
            <Button
              onClick={() => setTimeframe("monthly")}
              variant={timeframe === "monthly" ? "contained" : "outlined"}
            >
              Monthly
            </Button>
          </ButtonGroup>

          <ButtonGroup size="small" variant="outlined">
            <Button
              onClick={() => setPeriod(30)}
              variant={period === 30 ? "contained" : "outlined"}
            >
              30 periods
            </Button>
            <Button
              onClick={() => setPeriod(90)}
              variant={period === 90 ? "contained" : "outlined"}
            >
              90 periods
            </Button>
            <Button
              onClick={() => setPeriod(252)}
              variant={period === 252 ? "contained" : "outlined"}
            >
              1 Year
            </Button>
          </ButtonGroup>
        </Box>

        {/* Price Summary */}
        {latestPrice && oldestPrice && (
          <Box sx={{ display: "flex", gap: 2, mb: 2, flexWrap: "wrap" }}>
            <Chip
              label={`Current: ${formatPrice(latestPrice.close)}`}
              color="primary"
              variant="outlined"
            />
            <Chip
              icon={priceChange >= 0 ? <TrendingUp /> : <TrendingDown />}
              label={`${priceChange >= 0 ? "+" : ""}${formatPrice(priceChange)} (${priceChangePct.toFixed(2)}%)`}
              color={priceChange >= 0 ? "success" : "error"}
              variant="outlined"
            />
            <Chip
              label={`Volume: ${latestPrice.volume?.toLocaleString() || "N/A"}`}
              variant="outlined"
            />
          </Box>
        )}

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

        {/* Chart */}
        {!isLoading && !error && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={[...chartData].reverse()}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                tickFormatter={formatDate}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                domain={["auto", "auto"]}
                tickFormatter={(value) => `$${value?.toFixed(2)}`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="close"
                stroke="#1976d2"
                strokeWidth={2}
                dot={false}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
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
              Showing {(chartData?.length || 0)} {timeframe} data points for {symbol}
              {latestPrice && ` • Latest: ${formatDate(latestPrice.date)}`}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default HistoricalPriceChart;
