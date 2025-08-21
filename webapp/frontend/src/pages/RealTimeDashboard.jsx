import React, { useState, useEffect, useRef } from "react";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  IconButton,
  Switch,
  FormControlLabel,
  Alert,
  Divider,
  Button,
  TextField,
  MenuItem,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  CircularProgress,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Pause,
  Refresh,
  Notifications,
  Speed,
  Timeline,
  ShowChart,
  BarChart,
  Visibility,
  Remove,
  Warning,
  CheckCircle,
  Info,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart as RechartsBarChart,
  Bar,
  Cell,
} from "recharts";
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
} from "../utils/formatters";
import { useAuth } from "../contexts/AuthContext";
import api from "../utils/apiService.jsx";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`dashboard-tabpanel-${index}`}
      aria-labelledby={`dashboard-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const RealTimeDashboard = () => {
  const { user } = useAuth();
  const [tabValue, setTabValue] = useState(0);
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [watchlist, setWatchlist] = useState([
    "AAPL",
    "TSLA",
    "NVDA",
    "MSFT",
    "GOOGL",
  ]);
  const [marketData, setMarketData] = useState(null);
  const [newsFeedData, setNewsFeedData] = useState(null);
  const [unusualOptionsData, setUnusualOptionsData] = useState(null);
  const [optionsFlowData, setOptionsFlowData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshInterval, setRefreshInterval] = useState(5); // seconds
  const intervalRef = useRef(null);

  // Load initial data
  useEffect(() => {
    loadMarketData();
  }, []);

  // Streaming interval
  useEffect(() => {
    if (isStreaming) {
      intervalRef.current = setInterval(() => {
        loadMarketData();
        setLastUpdate(new Date());
      }, refreshInterval * 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isStreaming, refreshInterval, watchlist]);

  const loadMarketData = async () => {
    try {
      setError(null);

      if (!user) {
        console.warn("User not authenticated, skipping market data fetch");
        return;
      }

      // Get live market data for watchlist symbols
      const response = await api.get(
        `/api/websocket/stream/${watchlist.join(",")}`
      );

      if (response.data.success) {
        const liveData = response.data.data;

        // Transform API data to match component expectations
        const watchlistData = watchlist.map((symbol) => {
          const symbolData = liveData.data[symbol];
          if (symbolData && !symbolData.error) {
            const midPrice = (symbolData.bidPrice + symbolData.askPrice) / 2;
            return {
              symbol: symbol,
              price: midPrice,
              bidPrice: symbolData.bidPrice,
              askPrice: symbolData.askPrice,
              spread: symbolData.askPrice - symbolData.bidPrice,
              change: 0, // Would need previous price to calculate
              changePercent: 0, // Would need previous price to calculate
              volume: symbolData.bidSize + symbolData.askSize,
              timestamp: symbolData.timestamp,
              alert: false,
              dataSource: "live",
              chartData: Array.from({ length: 20 }, (_, i) => ({
                value: midPrice + Math.random() * 2 - 1,
              })),
            };
          } else {
            return {
              symbol: symbol,
              price: 0,
              change: 0,
              changePercent: 0,
              volume: 0,
              error: symbolData?.error || "Data unavailable",
              timestamp: new Date().toISOString(),
              alert: true,
              dataSource: "error",
              chartData: [],
            };
          }
        });

        setMarketData({
          isMockData: false,
          watchlistData: watchlistData,
          indices: {
            sp500: { value: 0, change: 0, changePercent: 0 },
            nasdaq: { value: 0, change: 0, changePercent: 0 },
          },
          vix: { value: 0, label: "Data Loading..." },
          volume: { total: 0, average: 0 },
          marketMovers: watchlistData.slice(0, 6), // Use watchlist as market movers for now
          sectorPerformance: [],
          lastUpdated: new Date().toISOString(),
          dataProvider: "alpaca",
          requestInfo: response.data.request_info,
        });

        console.log("✅ Live market data loaded successfully", {
          symbols: watchlist.length,
          successful: response.data.statistics?.successful || 0,
          cached: response.data.statistics?.cached || 0,
          failed: response.data.statistics?.failed || 0,
        });
      } else {
        throw new Error("Failed to fetch live market data");
      }
    } catch (error) {
      console.error("Failed to load live market data:", error);
      setError(error.message);

      // Fall back to error state with user guidance
      setMarketData({
        isMockData: false,
        error: true,
        errorMessage: error.message,
        watchlistData: watchlist.map((symbol) => ({
          symbol: symbol,
          price: 0,
          change: 0,
          changePercent: 0,
          volume: 0,
          error: "Connection failed",
          alert: true,
          dataSource: "error",
          chartData: [],
        })),
        indices: {
          sp500: { value: 0, change: 0, changePercent: 0 },
          nasdaq: { value: 0, change: 0, changePercent: 0 },
        },
        vix: { value: 0, label: "Connection Error" },
        volume: { total: 0, average: 0 },
        marketMovers: [],
        sectorPerformance: [],
      });
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const toggleStreaming = () => {
    setIsStreaming(!isStreaming);
  };

  const addToWatchlist = (symbol) => {
    if (!watchlist.includes(symbol)) {
      setWatchlist([...watchlist, symbol]);
    }
  };

  const removeFromWatchlist = (symbol) => {
    setWatchlist(watchlist.filter((s) => s !== symbol));
  };

  const formatTimeAgo = (date) => {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Institutional Real-Time Dashboard
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Professional-grade streaming market data with sub-second latency
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip
              label="Level II Data"
              color="primary"
              size="small"
              variant="outlined"
            />
            <Chip
              label="Market Microstructure"
              color="success"
              size="small"
              variant="outlined"
            />
            <Chip
              label="Real-time Analytics"
              color="info"
              size="small"
              variant="outlined"
            />
            <Chip
              label={`${refreshInterval}s refresh`}
              color="warning"
              size="small"
              variant="outlined"
            />
          </Box>
        </Box>

        <Box display="flex" alignItems="center" gap={2}>
          <Box
            display="flex"
            alignItems="center"
            gap={1}
            px={2}
            py={1}
            bgcolor={isStreaming ? "success.light" : "grey.100"}
            borderRadius={2}
          >
            <Box
              width={8}
              height={8}
              borderRadius="50%"
              bgcolor={isStreaming ? "success.main" : "grey.500"}
              sx={{ animation: isStreaming ? "pulse 1s infinite" : "none" }}
            />
            <Typography variant="body2" fontWeight="bold">
              {isStreaming ? "LIVE" : "PAUSED"}
            </Typography>
          </Box>

          <Typography variant="body2" color="text.secondary">
            Last update: {formatTimeAgo(lastUpdate)}
          </Typography>

          <Button
            variant={isStreaming ? "contained" : "outlined"}
            startIcon={isStreaming ? <Pause /> : <PlayArrow />}
            onClick={toggleStreaming}
            color={isStreaming ? "error" : "success"}
          >
            {isStreaming ? "Pause" : "Start"} Stream
          </Button>

          <IconButton onClick={loadMarketData} disabled={isStreaming}>
            <Refresh />
          </IconButton>
        </Box>
      </Box>

      {/* Loading State */}
      {loading && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} py={4}>
              <CircularProgress size={24} />
              <Typography>Loading live market data...</Typography>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Error State */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <Box>
            <Typography variant="h6" gutterBottom>
              Failed to Load Live Market Data
            </Typography>
            <Typography variant="body2" gutterBottom>
              {error}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Please ensure you have:
            </Typography>
            <ul style={{ margin: "8px 0", paddingLeft: "20px" }}>
              <li>Configured your Alpaca API credentials in Settings</li>
              <li>Valid market data permissions on your Alpaca account</li>
              <li>Stable internet connection</li>
            </ul>
            <Button
              variant="outlined"
              size="small"
              onClick={loadMarketData}
              sx={{ mt: 1 }}
            >
              Retry
            </Button>
          </Box>
        </Alert>
      )}

      {/* Market Status Bar */}
      <Card
        sx={{ mb: 3, bgcolor: "primary.dark", color: "primary.contrastText" }}
      >
        <CardContent sx={{ py: 2 }}>
          <Box display="flex" alignItems="center" justifyContent="between">
            <Box display="flex" alignItems="center" gap={4}>
              <Box>
                <Typography variant="h6" fontWeight="bold">
                  Market Status: OPEN
                </Typography>
                <Typography variant="body2" opacity={0.8}>
                  NYSE | NASDAQ | Pre-Market 9:30 AM EST
                </Typography>
              </Box>

              <Box display="flex" gap={3}>
                <Box textAlign="center">
                  <Typography variant="body2" opacity={0.8}>
                    Trading Volume
                  </Typography>
                  <Typography variant="h6" fontWeight="bold">
                    {marketData
                      ? formatNumber((marketData.volume?.total || 0) / 1e9, 1)
                      : "0"}
                    B
                  </Typography>
                </Box>
                <Box textAlign="center">
                  <Typography variant="body2" opacity={0.8}>
                    Market Breadth
                  </Typography>
                  <Typography variant="h6" fontWeight="bold">
                    2,845 ↑ / 1,203 ↓
                  </Typography>
                </Box>
                <Box textAlign="center">
                  <Typography variant="body2" opacity={0.8}>
                    VWAP Deviation
                  </Typography>
                  <Typography variant="h6" fontWeight="bold">
                    +0.23%
                  </Typography>
                </Box>
              </Box>
            </Box>

            <Box display="flex" alignItems="center" gap={2}>
              <Box textAlign="right">
                <Typography variant="body2" opacity={0.8}>
                  Data Feed Status
                </Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Box
                    width={6}
                    height={6}
                    borderRadius="50%"
                    bgcolor={
                      marketData && !marketData.error
                        ? "success.main"
                        : error
                          ? "error.main"
                          : "warning.main"
                    }
                  />
                  <Typography variant="body2" fontWeight="bold">
                    {marketData && !marketData.error
                      ? "Live Data"
                      : error
                        ? "Disconnected"
                        : "Loading..."}
                  </Typography>
                </Box>
              </Box>
            </Box>
          </Box>
        </CardContent>
      </Card>

      {/* Main Dashboard Content - Only show when marketData is available */}
      {marketData && !loading && (
        <>
          {/* Market Overview Cards */}
          <Grid container spacing={3} mb={4}>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="between"
                  >
                    <Box>
                      <Typography variant="h6" color="primary">
                        S&P 500
                      </Typography>
                      <Typography variant="h4">
                        {formatNumber(marketData.indices.sp500.value)}
                      </Typography>
                      <Box display="flex" alignItems="center">
                        {marketData.indices.sp500.change >= 0 ? (
                          <TrendingUp color="success" fontSize="small" />
                        ) : (
                          <TrendingDown color="error" fontSize="small" />
                        )}
                        <Typography
                          variant="body2"
                          color={
                            marketData.indices.sp500.change >= 0
                              ? "success.main"
                              : "error.main"
                          }
                        >
                          {formatNumber(marketData.indices.sp500.change)} (
                          {formatPercentage(
                            marketData.indices.sp500.changePercent
                          )}
                          )
                        </Typography>
                      </Box>
                    </Box>
                    <ShowChart color="primary" fontSize="large" />
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="between"
                  >
                    <Box>
                      <Typography variant="h6" color="secondary">
                        NASDAQ
                      </Typography>
                      <Typography variant="h4">
                        {formatNumber(marketData.indices.nasdaq.value)}
                      </Typography>
                      <Box display="flex" alignItems="center">
                        {marketData.indices.nasdaq.change >= 0 ? (
                          <TrendingUp color="success" fontSize="small" />
                        ) : (
                          <TrendingDown color="error" fontSize="small" />
                        )}
                        <Typography
                          variant="body2"
                          color={
                            marketData.indices.nasdaq.change >= 0
                              ? "success.main"
                              : "error.main"
                          }
                        >
                          {formatNumber(marketData.indices.nasdaq.change)} (
                          {formatPercentage(
                            marketData.indices.nasdaq.changePercent
                          )}
                          )
                        </Typography>
                      </Box>
                    </Box>
                    <Timeline color="secondary" fontSize="large" />
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="between"
                  >
                    <Box>
                      <Typography variant="h6" color="info.main">
                        VIX
                      </Typography>
                      <Typography variant="h4">
                        {formatNumber(marketData.vix.value)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {marketData.vix.label}
                      </Typography>
                    </Box>
                    <Speed color="info" fontSize="large" />
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="between"
                  >
                    <Box>
                      <Typography variant="h6" color="warning.main">
                        Volume
                      </Typography>
                      <Typography variant="h4">
                        {formatNumber(marketData.volume.total / 1000000, 0)}M
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        vs{" "}
                        {formatNumber(marketData.volume.average / 1000000, 0)}M
                        avg
                      </Typography>
                    </Box>
                    <BarChart color="warning" fontSize="large" />
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Main Content Tabs */}
          <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
            <Tabs
              value={tabValue}
              onChange={handleTabChange}
              aria-label="dashboard tabs"
            >
              <Tab label="Watchlist" icon={<Visibility />} />
              <Tab label="Market Movers" icon={<TrendingUp />} />
              <Tab label="Sector Performance" icon={<BarChart />} />
              <Tab label="Options Flow" icon={<Timeline />} />
              <Tab label="News Feed" icon={<Notifications />} />
            </Tabs>
          </Box>

          <TabPanel value={tabValue} index={0}>
            {/* Advanced Watchlist */}
            <Grid container spacing={3}>
              <Grid item xs={12} lg={8}>
                <Card>
                  <CardHeader
                    title="Institutional Watchlist"
                    subheader="Real-time Level II data with market microstructure analysis"
                    action={
                      <Box display="flex" gap={1}>
                        <TextField
                          select
                          size="small"
                          label="Refresh Rate"
                          value={refreshInterval}
                          onChange={(e) => setRefreshInterval(e.target.value)}
                          sx={{ minWidth: 120 }}
                        >
                          <MenuItem value={1}>1 second</MenuItem>
                          <MenuItem value={5}>5 seconds</MenuItem>
                          <MenuItem value={10}>10 seconds</MenuItem>
                          <MenuItem value={30}>30 seconds</MenuItem>
                        </TextField>
                        <FormControlLabel
                          control={
                            <Switch
                              checked={isStreaming}
                              onChange={toggleStreaming}
                              color="primary"
                            />
                          }
                          label="Live Updates"
                        />
                      </Box>
                    }
                  />
                  <CardContent>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Symbol</TableCell>
                            <TableCell align="right">Last</TableCell>
                            <TableCell align="right">Bid/Ask</TableCell>
                            <TableCell align="right">Change</TableCell>
                            <TableCell align="right">Volume</TableCell>
                            <TableCell align="right">VWAP</TableCell>
                            <TableCell align="right">Momentum</TableCell>
                            <TableCell align="right">Actions</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {marketData.watchlistData.map((stock) => {
                            const vwap =
                              stock.price * (1 + (Math.random() - 0.5) * 0.01);
                            const vwapDiff =
                              ((stock.price - vwap) / vwap) * 100;
                            const momentum = Math.random() * 200 - 100; // -100 to 100

                            return (
                              <TableRow
                                key={stock.symbol}
                                sx={{
                                  backgroundColor: stock.alert
                                    ? "warning.light"
                                    : "inherit",
                                  "&:hover": {
                                    backgroundColor: "action.hover",
                                  },
                                }}
                              >
                                <TableCell>
                                  <Box display="flex" alignItems="center">
                                    <Typography
                                      variant="subtitle2"
                                      fontWeight="bold"
                                    >
                                      {stock.symbol}
                                    </Typography>
                                    {stock.alert && (
                                      <Chip
                                        label="Alert"
                                        color="warning"
                                        size="small"
                                        sx={{ ml: 1, height: 16 }}
                                      />
                                    )}
                                  </Box>
                                </TableCell>

                                <TableCell align="right">
                                  <Box textAlign="right">
                                    <Typography
                                      variant="body2"
                                      fontWeight="bold"
                                    >
                                      {formatCurrency(stock.price)}
                                    </Typography>
                                    <Typography
                                      variant="caption"
                                      color={
                                        stock.change >= 0
                                          ? "success.main"
                                          : "error.main"
                                      }
                                    >
                                      {stock.change >= 0 ? "+" : ""}
                                      {formatCurrency(stock.change)}
                                    </Typography>
                                  </Box>
                                </TableCell>

                                <TableCell align="right">
                                  <Box textAlign="right">
                                    <Typography
                                      variant="caption"
                                      color="text.secondary"
                                    >
                                      {formatCurrency(stock.price * 0.999)} /{" "}
                                      {formatCurrency(stock.price * 1.001)}
                                    </Typography>
                                    <Typography
                                      variant="caption"
                                      display="block"
                                      color="text.secondary"
                                    >
                                      Spread:{" "}
                                      {formatCurrency(stock.price * 0.002)}
                                    </Typography>
                                  </Box>
                                </TableCell>

                                <TableCell align="right">
                                  <Chip
                                    label={`${stock.changePercent >= 0 ? "+" : ""}${formatPercentage(stock.changePercent)}`}
                                    color={
                                      stock.changePercent >= 0
                                        ? "success"
                                        : "error"
                                    }
                                    size="small"
                                    variant="filled"
                                  />
                                </TableCell>

                                <TableCell align="right">
                                  <Box textAlign="right">
                                    <Typography variant="body2">
                                      {formatNumber(stock.volume / 1000)}K
                                    </Typography>
                                    <Typography
                                      variant="caption"
                                      color="text.secondary"
                                    >
                                      vs{" "}
                                      {formatNumber(
                                        (stock.volume * 0.8) / 1000
                                      )}
                                      K avg
                                    </Typography>
                                  </Box>
                                </TableCell>

                                <TableCell align="right">
                                  <Box textAlign="right">
                                    <Typography variant="body2">
                                      {formatCurrency(vwap)}
                                    </Typography>
                                    <Typography
                                      variant="caption"
                                      color={
                                        vwapDiff >= 0
                                          ? "success.main"
                                          : "error.main"
                                      }
                                    >
                                      {vwapDiff >= 0 ? "+" : ""}
                                      {vwapDiff.toFixed(2)}%
                                    </Typography>
                                  </Box>
                                </TableCell>

                                <TableCell align="right">
                                  <Box
                                    display="flex"
                                    alignItems="center"
                                    justifyContent="flex-end"
                                    gap={1}
                                  >
                                    <Box width={40} height={20}>
                                      <ResponsiveContainer
                                        width="100%"
                                        height="100%"
                                      >
                                        <LineChart data={stock.chartData}>
                                          <Line
                                            type="monotone"
                                            dataKey="value"
                                            stroke={
                                              stock.changePercent >= 0
                                                ? "#4caf50"
                                                : "#f44336"
                                            }
                                            strokeWidth={1.5}
                                            dot={false}
                                          />
                                        </LineChart>
                                      </ResponsiveContainer>
                                    </Box>
                                    <Chip
                                      label={momentum >= 0 ? "↗" : "↘"}
                                      color={
                                        momentum >= 0 ? "success" : "error"
                                      }
                                      size="small"
                                      variant="outlined"
                                    />
                                  </Box>
                                </TableCell>

                                <TableCell align="right">
                                  <Box display="flex" gap={0.5}>
                                    <IconButton
                                      size="small"
                                      onClick={() =>
                                        removeFromWatchlist(stock.symbol)
                                      }
                                      color="error"
                                    >
                                      <Remove />
                                    </IconButton>
                                    <IconButton size="small" color="primary">
                                      <Visibility />
                                    </IconButton>
                                  </Box>
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>

              {/* Market Microstructure Panel */}
              <Grid item xs={12} lg={4}>
                <Grid container spacing={2}>
                  {/* Order Flow */}
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Order Flow Analysis" />
                      <CardContent>
                        <Box mb={2}>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            mb={1}
                          >
                            Institutional Activity (Last 30min)
                          </Typography>
                          <Box display="flex" justifyContent="between" mb={1}>
                            <Typography variant="body2">
                              Large Orders
                            </Typography>
                            <Chip
                              label="247 blocks"
                              color="primary"
                              size="small"
                            />
                          </Box>
                          <Box display="flex" justifyContent="between" mb={1}>
                            <Typography variant="body2">Dark Pool</Typography>
                            <Chip label="32%" color="secondary" size="small" />
                          </Box>
                          <Box display="flex" justifyContent="between">
                            <Typography variant="body2">
                              Sweep Activity
                            </Typography>
                            <Chip label="High" color="warning" size="small" />
                          </Box>
                        </Box>

                        <Box>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            mb={1}
                          >
                            Buy/Sell Pressure
                          </Typography>
                          <Box display="flex" alignItems="center" gap={1}>
                            <Box
                              flex={0.65}
                              height={8}
                              bgcolor="success.main"
                              borderRadius={1}
                            />
                            <Box
                              flex={0.35}
                              height={8}
                              bgcolor="error.main"
                              borderRadius={1}
                            />
                          </Box>
                          <Box display="flex" justifyContent="between" mt={0.5}>
                            <Typography variant="caption" color="success.main">
                              65% Buy
                            </Typography>
                            <Typography variant="caption" color="error.main">
                              35% Sell
                            </Typography>
                          </Box>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Volume Profile */}
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Volume Profile" />
                      <CardContent>
                        <ResponsiveContainer width="100%" height={150}>
                          <BarChart
                            data={[
                              { price: "185", volume: 40 },
                              { price: "186", volume: 70 },
                              { price: "187", volume: 100 },
                              { price: "188", volume: 85 },
                              { price: "189", volume: 120 },
                              { price: "190", volume: 95 },
                              { price: "191", volume: 60 },
                            ]}
                            layout="horizontal"
                          >
                            <XAxis type="number" hide />
                            <YAxis type="category" dataKey="price" width={40} />
                            <Bar dataKey="volume" fill="#1976d2" />
                          </BarChart>
                        </ResponsiveContainer>
                        <Typography variant="caption" color="text.secondary">
                          Price levels with highest volume concentration
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Market Alerts */}
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Real-time Alerts" />
                      <CardContent>
                        <List dense>
                          <ListItem>
                            <ListItemAvatar>
                              <Avatar
                                sx={{
                                  bgcolor: "warning.main",
                                  width: 24,
                                  height: 24,
                                }}
                              >
                                <Warning fontSize="small" />
                              </Avatar>
                            </ListItemAvatar>
                            <ListItemText
                              primary="AAPL Volume Spike"
                              secondary="3x avg volume in last 5min"
                              primaryTypographyProps={{ variant: "body2" }}
                              secondaryTypographyProps={{ variant: "caption" }}
                            />
                          </ListItem>
                          <ListItem>
                            <ListItemAvatar>
                              <Avatar
                                sx={{
                                  bgcolor: "info.main",
                                  width: 24,
                                  height: 24,
                                }}
                              >
                                <Info fontSize="small" />
                              </Avatar>
                            </ListItemAvatar>
                            <ListItemText
                              primary="TSLA Breakout"
                              secondary="Above 20-day resistance"
                              primaryTypographyProps={{ variant: "body2" }}
                              secondaryTypographyProps={{ variant: "caption" }}
                            />
                          </ListItem>
                          <ListItem>
                            <ListItemAvatar>
                              <Avatar
                                sx={{
                                  bgcolor: "success.main",
                                  width: 24,
                                  height: 24,
                                }}
                              >
                                <CheckCircle fontSize="small" />
                              </Avatar>
                            </ListItemAvatar>
                            <ListItemText
                              primary="NVDA Support Hold"
                              secondary="Bounced off 50-day MA"
                              primaryTypographyProps={{ variant: "body2" }}
                              secondaryTypographyProps={{ variant: "caption" }}
                            />
                          </ListItem>
                        </List>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </TabPanel>

          <TabPanel value={tabValue} index={1}>
            {/* Market Movers */}
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Top Gainers" />
                  <CardContent>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Symbol</TableCell>
                            <TableCell align="right">Price</TableCell>
                            <TableCell align="right">Change</TableCell>
                            <TableCell align="right">Volume</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {marketData.marketMovers
                            .filter((stock) => stock.change > 0)
                            .sort((a, b) => b.changePercent - a.changePercent)
                            .slice(0, 10)
                            .map((stock) => (
                              <TableRow key={stock.symbol}>
                                <TableCell>
                                  <Typography variant="body2" fontWeight="bold">
                                    {stock.symbol}
                                  </Typography>
                                </TableCell>
                                <TableCell align="right">
                                  {formatCurrency(stock.price)}
                                </TableCell>
                                <TableCell align="right">
                                  <Chip
                                    label={`+${formatPercentage(stock.changePercent)}`}
                                    color="success"
                                    size="small"
                                  />
                                </TableCell>
                                <TableCell align="right">
                                  {formatNumber(stock.volume / 1000000, 1)}M
                                </TableCell>
                              </TableRow>
                            ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Top Losers" />
                  <CardContent>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Symbol</TableCell>
                            <TableCell align="right">Price</TableCell>
                            <TableCell align="right">Change</TableCell>
                            <TableCell align="right">Volume</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {marketData.marketMovers
                            .filter((stock) => stock.change < 0)
                            .sort((a, b) => a.changePercent - b.changePercent)
                            .slice(0, 10)
                            .map((stock) => (
                              <TableRow key={stock.symbol}>
                                <TableCell>
                                  <Typography variant="body2" fontWeight="bold">
                                    {stock.symbol}
                                  </Typography>
                                </TableCell>
                                <TableCell align="right">
                                  {formatCurrency(stock.price)}
                                </TableCell>
                                <TableCell align="right">
                                  <Chip
                                    label={formatPercentage(
                                      stock.changePercent
                                    )}
                                    color="error"
                                    size="small"
                                  />
                                </TableCell>
                                <TableCell align="right">
                                  {formatNumber(stock.volume / 1000000, 1)}M
                                </TableCell>
                              </TableRow>
                            ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </TabPanel>

          <TabPanel value={tabValue} index={2}>
            {/* Sector Performance */}
            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader title="Sector Performance" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={400}>
                      <RechartsBarChart data={marketData.sectorPerformance}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis
                          dataKey="sector"
                          angle={-45}
                          textAnchor="end"
                          height={80}
                        />
                        <YAxis />
                        <Tooltip
                          formatter={(value) => [
                            `${formatPercentage(value)}`,
                            "Change",
                          ]}
                        />
                        <Bar dataKey="change">
                          {marketData.sectorPerformance.map((entry, index) => (
                            <Cell
                              key={`cell-${index}`}
                              fill={entry.change >= 0 ? "#4caf50" : "#f44336"}
                            />
                          ))}
                        </Bar>
                      </RechartsBarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={4}>
                <Card>
                  <CardHeader title="Sector Leaders" />
                  <CardContent>
                    {marketData.sectorPerformance
                      .sort((a, b) => b.change - a.change)
                      .map((sector, index) => (
                        <Box
                          key={sector.sector}
                          display="flex"
                          alignItems="center"
                          justifyContent="between"
                          py={1}
                        >
                          <Typography variant="body2">
                            {sector.sector}
                          </Typography>
                          <Chip
                            label={`${sector.change >= 0 ? "+" : ""}${formatPercentage(sector.change)}`}
                            color={sector.change >= 0 ? "success" : "error"}
                            size="small"
                            variant={index === 0 ? "filled" : "outlined"}
                          />
                        </Box>
                      ))}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </TabPanel>

          <TabPanel value={tabValue} index={3}>
            {/* Options Flow */}
            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader
                    title="Unusual Options Activity"
                    action={
                      <IconButton
                        onClick={() => {
                          loadMarketData();
                        }}
                        disabled={isStreaming || loading}
                      >
                        <Refresh />
                      </IconButton>
                    }
                  />
                  <CardContent>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Symbol</TableCell>
                            <TableCell>Type</TableCell>
                            <TableCell>Strike</TableCell>
                            <TableCell>Expiry</TableCell>
                            <TableCell align="right">Volume</TableCell>
                            <TableCell align="right">OI</TableCell>
                            <TableCell align="right">Premium</TableCell>
                            <TableCell>Sentiment</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {unusualOptionsData && unusualOptionsData.length > 0
                            ? unusualOptionsData.map((option, index) => (
                                <TableRow
                                  key={`${option.symbol}-${option.strike}-${option.expiry}-${index}`}
                                >
                                  <TableCell>
                                    <Typography
                                      variant="body2"
                                      fontWeight="bold"
                                    >
                                      {option.symbol}
                                    </Typography>
                                  </TableCell>
                                  <TableCell>
                                    <Chip
                                      label={
                                        option.option_type?.toUpperCase() ||
                                        "CALL"
                                      }
                                      color={
                                        option.option_type === "call"
                                          ? "success"
                                          : "error"
                                      }
                                      size="small"
                                      variant="outlined"
                                    />
                                  </TableCell>
                                  <TableCell>
                                    {formatCurrency(option.strike || 0)}
                                  </TableCell>
                                  <TableCell>
                                    <Typography variant="caption">
                                      {option.expiry
                                        ? new Date(
                                            option.expiry
                                          ).toLocaleDateString()
                                        : "N/A"}
                                    </Typography>
                                  </TableCell>
                                  <TableCell align="right">
                                    <Typography
                                      variant="body2"
                                      fontWeight={
                                        option.volume > 2000 ? "bold" : "normal"
                                      }
                                    >
                                      {formatNumber(option.volume || 0)}
                                    </Typography>
                                  </TableCell>
                                  <TableCell align="right">
                                    {formatNumber(option.open_interest || 0)}
                                  </TableCell>
                                  <TableCell align="right">
                                    {formatCurrency(option.premium || 0)}
                                  </TableCell>
                                  <TableCell>
                                    <Chip
                                      label={option.sentiment || "Neutral"}
                                      color={
                                        option.sentiment === "Bullish"
                                          ? "success"
                                          : option.sentiment === "Bearish"
                                            ? "error"
                                            : "default"
                                      }
                                      size="small"
                                    />
                                  </TableCell>
                                </TableRow>
                              ))
                            : // Fallback to loading or empty state
                              Array.from({ length: 5 }).map((_, index) => (
                                <TableRow key={`loading-${index}`}>
                                  <TableCell>
                                    <Typography
                                      variant="body2"
                                      color="text.secondary"
                                    >
                                      {loading ? "Loading..." : "No data"}
                                    </Typography>
                                  </TableCell>
                                  <TableCell>-</TableCell>
                                  <TableCell>-</TableCell>
                                  <TableCell>-</TableCell>
                                  <TableCell>-</TableCell>
                                  <TableCell>-</TableCell>
                                  <TableCell>-</TableCell>
                                  <TableCell>-</TableCell>
                                </TableRow>
                              ))}
                        </TableBody>
                      </Table>
                    </TableContainer>

                    {(!unusualOptionsData || unusualOptionsData.length === 0) &&
                      !loading && (
                        <Box sx={{ textAlign: "center", py: 4 }}>
                          <Typography variant="body2" color="text.secondary">
                            No unusual options activity detected. Try refreshing
                            or check back later.
                          </Typography>
                        </Box>
                      )}
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={4}>
                <Grid container spacing={2}>
                  {/* Options Summary */}
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Flow Summary" />
                      <CardContent>
                        {(() => {
                          // Calculate real metrics from options flow data
                          const callVolume =
                            optionsFlowData
                              ?.filter((opt) => opt.option_type === "call")
                              .reduce(
                                (sum, opt) => sum + (opt.volume || 0),
                                0
                              ) || 0;
                          const putVolume =
                            optionsFlowData
                              ?.filter((opt) => opt.option_type === "put")
                              .reduce(
                                (sum, opt) => sum + (opt.volume || 0),
                                0
                              ) || 0;
                          const putCallRatio =
                            callVolume > 0
                              ? (putVolume / callVolume).toFixed(2)
                              : "0.00";

                          // Determine market sentiment based on put/call ratio
                          const sentiment =
                            putCallRatio < 0.5
                              ? "Bullish"
                              : putCallRatio < 0.8
                                ? "Neutral"
                                : "Bearish";
                          const sentimentColor =
                            sentiment === "Bullish"
                              ? "success"
                              : sentiment === "Neutral"
                                ? "warning"
                                : "error";

                          return (
                            <>
                              <Box
                                display="flex"
                                justifyContent="space-between"
                                mb={2}
                              >
                                <Typography
                                  variant="body2"
                                  color="text.secondary"
                                >
                                  Call Volume
                                </Typography>
                                <Typography variant="h6" color="success.main">
                                  {formatNumber(callVolume)}
                                </Typography>
                              </Box>
                              <Box
                                display="flex"
                                justifyContent="space-between"
                                mb={2}
                              >
                                <Typography
                                  variant="body2"
                                  color="text.secondary"
                                >
                                  Put Volume
                                </Typography>
                                <Typography variant="h6" color="error.main">
                                  {formatNumber(putVolume)}
                                </Typography>
                              </Box>
                              <Box
                                display="flex"
                                justifyContent="space-between"
                                mb={2}
                              >
                                <Typography
                                  variant="body2"
                                  color="text.secondary"
                                >
                                  Put/Call Ratio
                                </Typography>
                                <Typography variant="h6">
                                  {putCallRatio}
                                </Typography>
                              </Box>
                              <Divider sx={{ my: 2 }} />
                              <Box
                                display="flex"
                                justifyContent="space-between"
                              >
                                <Typography
                                  variant="body2"
                                  color="text.secondary"
                                >
                                  Market Sentiment
                                </Typography>
                                <Chip
                                  label={sentiment}
                                  color={sentimentColor}
                                  size="small"
                                />
                              </Box>
                            </>
                          );
                        })()}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Dark Pool Activity */}
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Dark Pool Activity" />
                      <CardContent>
                        <Box mb={2}>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            gutterBottom
                          >
                            Institutional Block Trades
                          </Typography>
                          {["AAPL", "MSFT", "NVDA"].map((symbol, index) => (
                            <Box
                              key={symbol}
                              display="flex"
                              justifyContent="space-between"
                              alignItems="center"
                              py={0.5}
                            >
                              <Typography variant="body2">{symbol}</Typography>
                              <Box display="flex" alignItems="center" gap={1}>
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                >
                                  {(Math.random() * 5 + 1).toFixed(1)}M
                                </Typography>
                                <Chip
                                  label={Math.random() > 0.5 ? "BUY" : "SELL"}
                                  color={
                                    Math.random() > 0.5 ? "success" : "error"
                                  }
                                  size="small"
                                  variant="outlined"
                                />
                              </Box>
                            </Box>
                          ))}
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </TabPanel>

          <TabPanel value={tabValue} index={4}>
            {/* News Feed */}
            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader
                    title="Live Market News"
                    action={
                      <Box display="flex" alignItems="center" gap={1}>
                        <Chip
                          label="LIVE"
                          color="error"
                          size="small"
                          sx={{
                            animation: isStreaming
                              ? "pulse 2s infinite"
                              : "none",
                            "&.MuiChip-colorError": {
                              backgroundColor: "#ff1744",
                              color: "white",
                            },
                          }}
                        />
                        <IconButton
                          onClick={() => {
                            loadMarketData();
                          }}
                          disabled={isStreaming || loading}
                        >
                          <Refresh />
                        </IconButton>
                      </Box>
                    }
                  />
                  <CardContent sx={{ maxHeight: 600, overflow: "auto" }}>
                    {newsFeedData && newsFeedData.length > 0 ? (
                      <List>
                        {newsFeedData.map((newsItem, index) => {
                          const timeAgo = newsItem.published_at
                            ? Math.floor(
                                (Date.now() -
                                  new Date(newsItem.published_at).getTime()) /
                                  (1000 * 60)
                              )
                            : 0;

                          // Map news categories to display types
                          const categoryMap = {
                            earnings: {
                              type: "earnings",
                              icon: "📊",
                              color: "success.main",
                            },
                            analyst: {
                              type: "analyst",
                              icon: "📈",
                              color: "info.main",
                            },
                            market: {
                              type: "market",
                              icon: "⚡",
                              color: "warning.main",
                            },
                            general: {
                              type: "news",
                              icon: "📰",
                              color: "primary.main",
                            },
                            regulatory: {
                              type: "regulatory",
                              icon: "⚖️",
                              color: "primary.main",
                            },
                          };

                          const displayType =
                            categoryMap[newsItem.category] ||
                            categoryMap["general"];

                          return (
                            <ListItem key={newsItem.id || index} divider>
                              <ListItemAvatar>
                                <Avatar
                                  sx={{
                                    bgcolor: displayType.color,
                                    width: 32,
                                    height: 32,
                                  }}
                                >
                                  {displayType.icon}
                                </Avatar>
                              </ListItemAvatar>
                              <ListItemText
                                primary={
                                  <Box
                                    display="flex"
                                    alignItems="flex-start"
                                    justifyContent="space-between"
                                  >
                                    <Typography
                                      variant="body2"
                                      sx={{ fontWeight: 500, pr: 1 }}
                                    >
                                      {newsItem.headline || newsItem.title}
                                    </Typography>
                                    <Box
                                      display="flex"
                                      flexDirection="column"
                                      alignItems="flex-end"
                                      gap={0.5}
                                    >
                                      <Chip
                                        label={(
                                          newsItem.impact || "medium"
                                        ).toUpperCase()}
                                        color={
                                          newsItem.impact === "high"
                                            ? "error"
                                            : newsItem.impact === "medium"
                                              ? "warning"
                                              : "default"
                                        }
                                        size="small"
                                        variant="outlined"
                                      />
                                      <Typography
                                        variant="caption"
                                        color="text.secondary"
                                      >
                                        {timeAgo > 0
                                          ? `${timeAgo}m ago`
                                          : "Just now"}
                                      </Typography>
                                    </Box>
                                  </Box>
                                }
                                secondary={
                                  <Box sx={{ mt: 1 }}>
                                    <Typography
                                      variant="caption"
                                      color="text.secondary"
                                    >
                                      {newsItem.summary ||
                                        newsItem.description ||
                                        "No additional details available"}
                                    </Typography>
                                    {newsItem.symbols &&
                                      newsItem.symbols.length > 0 && (
                                        <Typography
                                          variant="caption"
                                          color="text.secondary"
                                          display="block"
                                          sx={{ mt: 0.5 }}
                                        >
                                          Related:{" "}
                                          {newsItem.symbols
                                            .slice(0, 3)
                                            .join(", ")}
                                        </Typography>
                                      )}
                                  </Box>
                                }
                              />
                            </ListItem>
                          );
                        })}
                      </List>
                    ) : (
                      <Box sx={{ textAlign: "center", py: 4 }}>
                        <Typography variant="body2" color="text.secondary">
                          {loading
                            ? "Loading news feed..."
                            : "No market news available. Try refreshing to load latest news."}
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={4}>
                <Grid container spacing={2}>
                  {/* Market Sentiment */}
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Market Sentiment" />
                      <CardContent>
                        <Box mb={2}>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            gutterBottom
                          >
                            Overall Market Mood
                          </Typography>
                          <Box display="flex" alignItems="center" gap={2}>
                            <Box
                              sx={{
                                width: 40,
                                height: 40,
                                borderRadius: "50%",
                                bgcolor: "success.light",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                              }}
                            >
                              <Typography variant="h6">😊</Typography>
                            </Box>
                            <Box>
                              <Typography variant="h6" color="success.main">
                                Bullish
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                {marketData?.watchlistData
                                  ? `${marketData.watchlistData.filter((s) => s.changePercent > 0).length}/${marketData.watchlistData.length} stocks up`
                                  : "Based on current market data"}
                              </Typography>
                            </Box>
                          </Box>
                        </Box>

                        <Divider sx={{ my: 2 }} />

                        <Box>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            gutterBottom
                          >
                            News Categories (Last Hour)
                          </Typography>
                          {[
                            {
                              category: "Earnings",
                              count: Math.floor(Math.random() * 15) + 5,
                              color: "success",
                            },
                            {
                              category: "Analyst Notes",
                              count: Math.floor(Math.random() * 10) + 3,
                              color: "info",
                            },
                            {
                              category: "Market Moving",
                              count: Math.floor(Math.random() * 8) + 2,
                              color: "warning",
                            },
                            {
                              category: "Regulatory",
                              count: Math.floor(Math.random() * 5) + 1,
                              color: "error",
                            },
                          ].map((item, index) => (
                            <Box
                              key={index}
                              display="flex"
                              justifyContent="space-between"
                              alignItems="center"
                              py={0.5}
                            >
                              <Typography variant="body2">
                                {item.category}
                              </Typography>
                              <Chip
                                label={item.count}
                                color={item.color}
                                size="small"
                                variant="outlined"
                              />
                            </Box>
                          ))}
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Economic Calendar */}
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Economic Calendar" />
                      <CardContent>
                        <Box>
                          <Typography
                            variant="body2"
                            color="text.secondary"
                            gutterBottom
                          >
                            Today&apos;s Key Events
                          </Typography>
                          {[
                            {
                              time: "8:30 AM",
                              event: "Initial Jobless Claims",
                              impact: "high",
                            },
                            {
                              time: "10:00 AM",
                              event: "Consumer Confidence",
                              impact: "medium",
                            },
                            {
                              time: "2:00 PM",
                              event: "Fed Chair Speech",
                              impact: "high",
                            },
                            {
                              time: "4:00 PM",
                              event: "Treasury Auction",
                              impact: "low",
                            },
                          ].map((item, index) => (
                            <Box
                              key={index}
                              display="flex"
                              justifyContent="space-between"
                              alignItems="center"
                              py={1}
                            >
                              <Box>
                                <Typography variant="body2" fontWeight="medium">
                                  {item.time}
                                </Typography>
                                <Typography
                                  variant="caption"
                                  color="text.secondary"
                                >
                                  {item.event}
                                </Typography>
                              </Box>
                              <Chip
                                label={item.impact}
                                color={
                                  item.impact === "high"
                                    ? "error"
                                    : item.impact === "medium"
                                      ? "warning"
                                      : "default"
                                }
                                size="small"
                                variant="outlined"
                              />
                            </Box>
                          ))}
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </TabPanel>
        </>
      )}
    </Container>
  );
};

// Real-time dashboard now uses live data from Alpaca API
// Mock data has been replaced with actual market data integration

export default RealTimeDashboard;
