import React, { useState, useEffect } from "react";
import {
  Box,
  Grid,
  Paper,
  Typography,
  Tabs,
  Tab,
  Card,
  CardContent,
  TableContainer,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Chip,
  IconButton,
  Button,
  TextField,
  MenuItem,
  CircularProgress,
  Alert,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Refresh,
  Star,
  StarBorder,
  AccountBalanceWallet,
  Timeline,
  NewReleases,
  Security,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";

import { LoadingDisplay } from "../components/LoadingDisplay";
import ErrorBoundary from "../components/ErrorBoundary";
import apiService from "../utils/apiService.jsx";

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`crypto-tabpanel-${index}`}
      aria-labelledby={`crypto-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

function CryptoDashboard() {
  const [activeTab, setActiveTab] = useState(0);
  const [selectedTimeframe, setSelectedTimeframe] = useState("24h");
  const [watchlist, setWatchlist] = useState(["BTC", "ETH", "SOL", "AVAX"]);
  const [refreshKey, setRefreshKey] = useState(0);

  console.log("🚀 [CRYPTO-DASHBOARD] Rendering crypto dashboard");

  // Fetch market overview data
  const {
    data: marketOverview,
    isLoading: marketLoading,
    error: marketError,
    refetch: refetchMarket,
  } = useQuery({
    queryKey: ["cryptoMarketOverview", refreshKey],
    queryFn: () => apiService.get("/crypto/market-overview"),
    refetchInterval: 30000, // Refresh every 30 seconds
    staleTime: 25000,
    cacheTime: 60000,
  });

  // Fetch top cryptocurrencies
  const {
    data: topCoins,
    isLoading: topCoinsLoading,
    error: topCoinsError,
    refetch: refetchTopCoins,
  } = useQuery({
    queryKey: ["cryptoTopCoins", selectedTimeframe, refreshKey],
    queryFn: () =>
      apiService.get(`/crypto/top-coins?limit=50&order=market_cap_desc`),
    refetchInterval: 30000,
    staleTime: 25000,
    cacheTime: 60000,
  });

  // Fetch trending cryptocurrencies
  const {
    data: trending,
    isLoading: trendingLoading,
    error: trendingError,
    refetch: refetchTrending,
  } = useQuery({
    queryKey: ["cryptoTrending", selectedTimeframe, refreshKey],
    queryFn: () =>
      apiService.get(
        `/crypto/trending?timeframe=${selectedTimeframe}&limit=10`
      ),
    refetchInterval: 60000, // Refresh every minute
    staleTime: 50000,
    cacheTime: 120000,
  });

  // Fetch crypto news
  const {
    data: cryptoNews,
    isLoading: newsLoading,
    error: newsError,
    refetch: refetchNews,
  } = useQuery({
    queryKey: ["cryptoNews", selectedTimeframe, refreshKey],
    queryFn: () =>
      apiService.get(`/crypto/news?limit=20&timeframe=${selectedTimeframe}`),
    refetchInterval: 120000, // Refresh every 2 minutes
    staleTime: 100000,
    cacheTime: 300000,
  });

  // Fetch DeFi data
  const {
    data: defiData,
    isLoading: defiLoading,
    error: defiError,
    refetch: refetchDefi,
  } = useQuery({
    queryKey: ["cryptoDefi", refreshKey],
    queryFn: () => apiService.get("/crypto/defi?limit=20"),
    refetchInterval: 300000, // Refresh every 5 minutes
    staleTime: 240000,
    cacheTime: 600000,
  });

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
    console.log(`📊 [CRYPTO-DASHBOARD] Switched to tab ${newValue}`);
  };

  const handleTimeframeChange = (event) => {
    const newTimeframe = event.target.value;
    setSelectedTimeframe(newTimeframe);
    console.log(`⏱️ [CRYPTO-DASHBOARD] Changed timeframe to ${newTimeframe}`);
  };

  const handleRefresh = () => {
    console.log("🔄 [CRYPTO-DASHBOARD] Manual refresh triggered");
    setRefreshKey((prev) => prev + 1);
    refetchMarket();
    refetchTopCoins();
    refetchTrending();
    refetchNews();
    refetchDefi();
  };

  const toggleWatchlist = (symbol) => {
    setWatchlist((prev) =>
      prev.includes(symbol)
        ? prev.filter((s) => s !== symbol)
        : [...prev, symbol]
    );
    console.log(`⭐ [CRYPTO-DASHBOARD] Toggled ${symbol} in watchlist`);
  };

  const formatCurrency = (value, decimals = 2) => {
    if (!value && value !== 0) return "N/A";

    if (value >= 1000000000000) {
      return `$${(value / 1000000000000).toFixed(1)}T`;
    } else if (value >= 1000000000) {
      return `$${(value / 1000000000).toFixed(1)}B`;
    } else if (value >= 1000000) {
      return `$${(value / 1000000).toFixed(1)}M`;
    } else if (value >= 1000) {
      return `$${(value / 1000).toFixed(1)}K`;
    } else {
      return `$${Number(value).toFixed(decimals)}`;
    }
  };

  const formatPercentage = (value, showSign = true) => {
    if (!value && value !== 0) return "N/A";
    const formatted = `${Math.abs(value).toFixed(2)}%`;
    if (!showSign) return formatted;
    return value >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  const getPercentageColor = (value) => {
    if (!value && value !== 0) return "text.secondary";
    return value >= 0 ? "success.main" : "error.main";
  };

  const getPercentageIcon = (value) => {
    if (!value && value !== 0) return null;
    return value >= 0 ? <TrendingUp /> : <TrendingDown />;
  };

  const renderMarketOverview = () => {
    if (marketLoading)
      return <LoadingDisplay message="Loading market overview..." />;
    if (marketError)
      return <Alert severity="error">Failed to load market overview</Alert>;
    if (!marketOverview?.data)
      return <Alert severity="info">No market data available</Alert>;

    const overview = marketOverview.data;

    return (
      <Grid container spacing={3}>
        {/* Market Stats Cards */}
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Total Market Cap
              </Typography>
              <Typography variant="h4" color="primary">
                {formatCurrency(overview.market_cap_usd, 0)}
              </Typography>
              <Box display="flex" alignItems="center" mt={1}>
                {getPercentageIcon(overview.market_cap_change_24h)}
                <Typography
                  variant="body2"
                  color={getPercentageColor(overview.market_cap_change_24h)}
                  sx={{ ml: 0.5 }}
                >
                  {formatPercentage(overview.market_cap_change_24h)} (24h)
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                24h Volume
              </Typography>
              <Typography variant="h4" color="primary">
                {formatCurrency(overview.volume_24h_usd, 0)}
              </Typography>
              <Box display="flex" alignItems="center" mt={1}>
                {getPercentageIcon(overview.volume_change_24h)}
                <Typography
                  variant="body2"
                  color={getPercentageColor(overview.volume_change_24h)}
                  sx={{ ml: 0.5 }}
                >
                  {formatPercentage(overview.volume_change_24h)} (24h)
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                BTC Dominance
              </Typography>
              <Typography variant="h4" color="primary">
                {overview.btc_dominance?.toFixed(1)}%
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                ETH: {overview.eth_dominance?.toFixed(1)}%
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Fear & Greed
              </Typography>
              <Typography variant="h4" color="primary">
                {overview.fear_greed_index?.value}
              </Typography>
              <Chip
                label={overview.fear_greed_index?.label || "Neutral"}
                color={
                  overview.fear_greed_index?.value >= 70
                    ? "error"
                    : overview.fear_greed_index?.value >= 50
                      ? "warning"
                      : "success"
                }
                size="small"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  const renderTopCoins = () => {
    if (topCoinsLoading)
      return <LoadingDisplay message="Loading top cryptocurrencies..." />;
    if (topCoinsError)
      return <Alert severity="error">Failed to load cryptocurrency data</Alert>;
    if (!topCoins?.data?.coins)
      return <Alert severity="info">No cryptocurrency data available</Alert>;

    return (
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Rank</TableCell>
              <TableCell>Name</TableCell>
              <TableCell align="right">Price</TableCell>
              <TableCell align="right">24h Change</TableCell>
              <TableCell align="right">7d Change</TableCell>
              <TableCell align="right">Market Cap</TableCell>
              <TableCell align="right">Volume (24h)</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {topCoins.data.coins.map((coin) => (
              <TableRow key={coin.id} hover>
                <TableCell>{coin.rank}</TableCell>
                <TableCell>
                  <Box display="flex" alignItems="center">
                    <Box ml={1}>
                      <Typography variant="subtitle2">{coin.name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {coin.symbol}
                      </Typography>
                    </Box>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {formatCurrency(coin.price_usd)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="flex-end"
                  >
                    {getPercentageIcon(coin.change_24h)}
                    <Typography
                      variant="body2"
                      color={getPercentageColor(coin.change_24h)}
                      sx={{ ml: 0.5 }}
                    >
                      {formatPercentage(coin.change_24h)}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="flex-end"
                  >
                    {getPercentageIcon(coin.change_7d)}
                    <Typography
                      variant="body2"
                      color={getPercentageColor(coin.change_7d)}
                      sx={{ ml: 0.5 }}
                    >
                      {formatPercentage(coin.change_7d)}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {formatCurrency(coin.market_cap_usd, 0)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {formatCurrency(coin.volume_24h_usd, 0)}
                  </Typography>
                </TableCell>
                <TableCell align="center">
                  <IconButton
                    size="small"
                    onClick={() => toggleWatchlist(coin.symbol)}
                    color={
                      watchlist.includes(coin.symbol) ? "primary" : "default"
                    }
                  >
                    {watchlist.includes(coin.symbol) ? (
                      <Star />
                    ) : (
                      <StarBorder />
                    )}
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  };

  const renderTrending = () => {
    if (trendingLoading)
      return <LoadingDisplay message="Loading trending cryptocurrencies..." />;
    if (trendingError)
      return <Alert severity="error">Failed to load trending data</Alert>;
    if (!trending?.data?.trending)
      return <Alert severity="info">No trending data available</Alert>;

    return (
      <Grid container spacing={2}>
        {trending.data.trending.map((coin, index) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={coin.id}>
            <Card>
              <CardContent>
                <Box
                  display="flex"
                  justifyContent="space-between"
                  alignItems="flex-start"
                >
                  <Box>
                    <Typography variant="h6">{coin.symbol}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {coin.name}
                    </Typography>
                  </Box>
                  <Chip
                    label={`#${coin.rank}`}
                    size="small"
                    color="primary"
                    variant="outlined"
                  />
                </Box>

                <Box mt={2}>
                  <Typography variant="body2" color="text.secondary">
                    24h Change
                  </Typography>
                  <Box display="flex" alignItems="center">
                    {getPercentageIcon(coin.price_change_24h)}
                    <Typography
                      variant="h6"
                      color={getPercentageColor(coin.price_change_24h)}
                      sx={{ ml: 0.5 }}
                    >
                      {formatPercentage(coin.price_change_24h)}
                    </Typography>
                  </Box>
                </Box>

                <Box
                  mt={1}
                  display="flex"
                  justifyContent="space-between"
                  alignItems="center"
                >
                  <Typography variant="body2" color="text.secondary">
                    Trending Score: {coin.trending_score}
                  </Typography>
                  <IconButton
                    size="small"
                    onClick={() => toggleWatchlist(coin.symbol)}
                    color={
                      watchlist.includes(coin.symbol) ? "primary" : "default"
                    }
                  >
                    {watchlist.includes(coin.symbol) ? (
                      <Star />
                    ) : (
                      <StarBorder />
                    )}
                  </IconButton>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  };

  const renderNews = () => {
    if (newsLoading) return <LoadingDisplay message="Loading crypto news..." />;
    if (newsError)
      return <Alert severity="error">Failed to load crypto news</Alert>;
    if (!cryptoNews?.data?.articles)
      return <Alert severity="info">No news articles available</Alert>;

    return (
      <Grid container spacing={2}>
        {cryptoNews.data.articles.map((article, index) => (
          <Grid item xs={12} md={6} key={article.id}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {article.title}
                </Typography>

                <Typography variant="body2" color="text.secondary" paragraph>
                  {article.summary}
                </Typography>

                <Box
                  display="flex"
                  justifyContent="space-between"
                  alignItems="center"
                  mb={1}
                >
                  <Typography variant="caption" color="text.secondary">
                    {article.source} • {article.author}
                  </Typography>
                  <Chip
                    label={article.sentiment_label}
                    size="small"
                    color={
                      article.sentiment_label === "positive"
                        ? "success"
                        : article.sentiment_label === "negative"
                          ? "error"
                          : "default"
                    }
                  />
                </Box>

                <Box
                  display="flex"
                  justifyContent="space-between"
                  alignItems="center"
                >
                  <Typography variant="caption" color="text.secondary">
                    Impact Score: {article.impact_score}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(article.published_at).toLocaleDateString()}
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  };

  const renderDeFi = () => {
    if (defiLoading)
      return <LoadingDisplay message="Loading DeFi protocols..." />;
    if (defiError)
      return <Alert severity="error">Failed to load DeFi data</Alert>;
    if (!defiData?.data?.protocols)
      return <Alert severity="info">No DeFi data available</Alert>;

    return (
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Protocol</TableCell>
              <TableCell>Category</TableCell>
              <TableCell align="right">TVL</TableCell>
              <TableCell align="right">24h Change</TableCell>
              <TableCell align="right">24h Volume</TableCell>
              <TableCell align="right">Users (24h)</TableCell>
              <TableCell align="right">APY Range</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {defiData.data.protocols.map((protocol) => (
              <TableRow key={protocol.name} hover>
                <TableCell>
                  <Box>
                    <Typography variant="subtitle2">{protocol.name}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {protocol.symbol}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Chip
                    label={protocol.category}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {formatCurrency(protocol.tvl_usd, 0)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="flex-end"
                  >
                    {getPercentageIcon(protocol.tvl_change_24h)}
                    <Typography
                      variant="body2"
                      color={getPercentageColor(protocol.tvl_change_24h)}
                      sx={{ ml: 0.5 }}
                    >
                      {formatPercentage(protocol.tvl_change_24h)}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {formatCurrency(protocol.volume_24h, 0)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {protocol.users_24h?.toLocaleString()}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {protocol.apy_range?.min}% - {protocol.apy_range?.max}%
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  };

  return (
    <ErrorBoundary
      fallback={<Alert severity="error">Failed to load crypto dashboard</Alert>}
    >
      <Box sx={{ width: "100%", p: 3 }}>
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          mb={3}
        >
          <Typography variant="h4" component="h1">
            Cryptocurrency Dashboard
          </Typography>

          <Box display="flex" alignItems="center" gap={2}>
            <TextField
              select
              label="Timeframe"
              value={selectedTimeframe}
              onChange={handleTimeframeChange}
              size="small"
              sx={{ minWidth: 120 }}
            >
              <MenuItem value="1h">1 Hour</MenuItem>
              <MenuItem value="24h">24 Hours</MenuItem>
              <MenuItem value="7d">7 Days</MenuItem>
              <MenuItem value="30d">30 Days</MenuItem>
            </TextField>

            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={handleRefresh}
              size="small"
            >
              Refresh
            </Button>
          </Box>
        </Box>

        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
          <Tabs
            value={activeTab}
            onChange={handleTabChange}
            aria-label="crypto dashboard tabs"
          >
            <Tab
              label="Market Overview"
              icon={<Timeline />}
              iconPosition="start"
              id="crypto-tab-0"
              aria-controls="crypto-tabpanel-0"
            />
            <Tab
              label="Top Cryptocurrencies"
              icon={<TrendingUp />}
              iconPosition="start"
              id="crypto-tab-1"
              aria-controls="crypto-tabpanel-1"
            />
            <Tab
              label="Trending"
              icon={<NewReleases />}
              iconPosition="start"
              id="crypto-tab-2"
              aria-controls="crypto-tabpanel-2"
            />
            <Tab
              label="News & Sentiment"
              icon={<NewReleases />}
              iconPosition="start"
              id="crypto-tab-3"
              aria-controls="crypto-tabpanel-3"
            />
            <Tab
              label="DeFi Protocols"
              icon={<Security />}
              iconPosition="start"
              id="crypto-tab-4"
              aria-controls="crypto-tabpanel-4"
            />
          </Tabs>
        </Box>

        <TabPanel value={activeTab} index={0}>
          {renderMarketOverview()}
        </TabPanel>

        <TabPanel value={activeTab} index={1}>
          {renderTopCoins()}
        </TabPanel>

        <TabPanel value={activeTab} index={2}>
          {renderTrending()}
        </TabPanel>

        <TabPanel value={activeTab} index={3}>
          {renderNews()}
        </TabPanel>

        <TabPanel value={activeTab} index={4}>
          {renderDeFi()}
        </TabPanel>
      </Box>
    </ErrorBoundary>
  );
}

export default CryptoDashboard;
