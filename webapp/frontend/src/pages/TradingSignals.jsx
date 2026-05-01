import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "@mui/material/styles";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Tab,
  Tabs,
  TextField,
  Typography,
  InputAdornment,
  IconButton,
} from "@mui/material";
import {
  FilterList,
  Search,
  Clear,
} from "@mui/icons-material";
import api, { getApiConfig, extractResponseData } from "../services/api";
import { ErrorDisplay, LoadingDisplay } from "../components/ui/ErrorBoundary";
import ErrorBoundary from "../components/ErrorBoundary";
import SignalCardAccordion from "../components/SignalCardAccordion";

const logger = {
  info: (msg) => console.log(`[TradingSignals] ${msg}`),
  error: (msg) => console.error(`[TradingSignals] ${msg}`),
};

function TradingSignals() {
  useDocumentTitle("Trading Signals - All Strategies");
  const theme = useTheme();
  const { apiUrl: API_BASE } = getApiConfig();

  const [strategy, setStrategy] = useState("swing"); // swing, range, mean-reversion
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [signalFilter, setSignalFilter] = useState(""); // BUY, SELL, or empty for all
  const [days, setDays] = useState(180);
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [minVolume, setMinVolume] = useState("");
  const [maxVolume, setMaxVolume] = useState("");
  const [minRsi, setMinRsi] = useState("");
  const [maxRsi, setMaxRsi] = useState("");
  const [minAdx, setMinAdx] = useState("");
  const [sort, setSort] = useState("date");
  const [sortOrder, setSortOrder] = useState("DESC");

  // Map strategy names to API endpoints and titles
  const strategyConfig = {
    swing: {
      endpoint: "/api/signals",
      title: "Swing Trading Signals",
      description: "AI-powered swing trading signals with market stage analysis",
      color: theme.palette.primary.main,
    },
    range: {
      endpoint: "/api/signals/range",
      title: "Range Trading Signals",
      description: "Range bounce signals with position analysis and breakout quality",
      color: theme.palette.info.main,
    },
    "mean-reversion": {
      endpoint: "/api/signals/mean-reversion",
      title: "Mean Reversion Signals",
      description: "Connors RSI(2) oversold signals with confluence analysis",
      color: theme.palette.success.main,
    },
  };

  const config = strategyConfig[strategy];

  // Fetch signals based on selected strategy with all advanced filters
  const { data: signalsData, isLoading, isError, error } = useQuery({
    queryKey: ["unifiedSignals", strategy, symbolFilter, signalFilter, days, minPrice, maxPrice, minVolume, maxVolume, minRsi, maxRsi, minAdx, sort, sortOrder, page],
    queryFn: async () => {
      const params = new URLSearchParams();

      // Always use the new unified search endpoint
      params.append("type", strategy);
      if (symbolFilter) params.append("symbol", symbolFilter);
      if (signalFilter) params.append("signal", signalFilter);
      params.append("days", days);
      if (minPrice) params.append("min_price", minPrice);
      if (maxPrice) params.append("max_price", maxPrice);
      if (minVolume) params.append("min_volume", minVolume);
      if (maxVolume) params.append("max_volume", maxVolume);
      if (minRsi) params.append("min_rsi", minRsi);
      if (maxRsi) params.append("max_rsi", maxRsi);
      if (minAdx) params.append("min_adx", minAdx);
      params.append("limit", 100);
      params.append("page", page + 1);
      params.append("sort", sort);
      params.append("sort_order", sortOrder);

      const response = await api.get(`/api/signals/search?${params}`);
      return extractResponseData(response);
    },
  });

  const filteredSignals = signalsData?.items || [];

  const handleStrategyChange = (event, newValue) => {
    setStrategy(newValue);
    setPage(0);
  };

  const handleSymbolFilterChange = (e) => {
    setSymbolFilter(e.target.value);
    setPage(0);
  };

  const handleSignalFilterChange = (e) => {
    setSignalFilter(e.target.value);
    setPage(0);
  };

  const handleDaysChange = (e) => {
    setDays(e.target.value);
    setPage(0);
  };

  const handleSortChange = (e) => {
    setSort(e.target.value);
    setPage(0);
  };

  const handleSortOrderChange = (e) => {
    setSortOrder(e.target.value);
    setPage(0);
  };

  const handleClearFilters = () => {
    setSymbolFilter("");
    setSignalFilter("");
    setDays(180);
    setMinPrice("");
    setMaxPrice("");
    setMinVolume("");
    setMaxVolume("");
    setMinRsi("");
    setMaxRsi("");
    setMinAdx("");
    setSort("date");
    setSortOrder("DESC");
    setPage(0);
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h3"
          component="h1"
          gutterBottom
          sx={{ fontWeight: 700, color: "primary.main" }}
        >
          📊 Trading Signals
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 3 }}>
          Unified view of all trading strategies with complete metrics and analysis
        </Typography>
      </Box>

      {/* Strategy Tabs */}
      <Paper sx={{ mb: 4 }}>
        <Tabs
          value={strategy}
          onChange={handleStrategyChange}
          indicatorColor="primary"
          textColor="primary"
          sx={{ p: 2 }}
        >
          <Tab label="Swing Trading" value="swing" sx={{ fontWeight: 600 }} />
          <Tab label="Range Trading" value="range" sx={{ fontWeight: 600 }} />
          <Tab label="Mean Reversion" value="mean-reversion" sx={{ fontWeight: 600 }} />
        </Tabs>

        {/* Strategy Info */}
        <Box sx={{ px: 3, py: 2, backgroundColor: theme.palette.action.hover }}>
          <Typography variant="h5" sx={{ fontWeight: 700, color: config.color, mb: 1 }}>
            {config.title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {config.description}
          </Typography>
        </Box>
      </Paper>

      {/* Filters */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="flex-end">
            <Grid item xs={12}>
              <Typography variant="h6" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <FilterList />
                Advanced Filters
              </Typography>
              <Divider sx={{ mb: 2 }} />
            </Grid>

            {/* Symbol Search */}
            <Grid item xs={12} sm={6} md={3}>
              <TextField
                fullWidth
                size="small"
                label="Symbol"
                placeholder="e.g., AAPL"
                value={symbolFilter}
                onChange={handleSymbolFilterChange}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search fontSize="small" />
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>

            {/* Signal Type Filter */}
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Signal</InputLabel>
                <Select
                  value={signalFilter}
                  onChange={handleSignalFilterChange}
                  label="Signal"
                >
                  <MenuItem value="">All Signals</MenuItem>
                  <MenuItem value="BUY">BUY Only</MenuItem>
                  <MenuItem value="SELL">SELL Only</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            {/* Days Filter */}
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Time Period</InputLabel>
                <Select
                  value={days}
                  onChange={handleDaysChange}
                  label="Time Period"
                >
                  <MenuItem value={7}>Last 7 Days</MenuItem>
                  <MenuItem value={30}>Last 30 Days</MenuItem>
                  <MenuItem value={90}>Last 90 Days</MenuItem>
                  <MenuItem value={180}>Last 6 Months</MenuItem>
                  <MenuItem value={365}>Last Year</MenuItem>
                  <MenuItem value={3650}>All Time</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            {/* Sorting */}
            <Grid item xs={12} sm={6} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Sort By</InputLabel>
                <Select
                  value={sort}
                  onChange={handleSortChange}
                  label="Sort By"
                >
                  <MenuItem value="date">Date</MenuItem>
                  <MenuItem value="symbol">Symbol</MenuItem>
                  <MenuItem value="close">Price</MenuItem>
                  <MenuItem value="volume">Volume</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            {/* Sort Order */}
            <Grid item xs={12} sm={6} md={1}>
              <FormControl fullWidth size="small">
                <InputLabel>Order</InputLabel>
                <Select
                  value={sortOrder}
                  onChange={handleSortOrderChange}
                  label="Order"
                >
                  <MenuItem value="DESC">Descending</MenuItem>
                  <MenuItem value="ASC">Ascending</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            {/* Price Range */}
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Min Price"
                placeholder="0"
                value={minPrice}
                onChange={(e) => { setMinPrice(e.target.value); setPage(0); }}
              />
            </Grid>

            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Max Price"
                placeholder="10000"
                value={maxPrice}
                onChange={(e) => { setMaxPrice(e.target.value); setPage(0); }}
              />
            </Grid>

            {/* Volume Range */}
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Min Volume"
                placeholder="0"
                value={minVolume}
                onChange={(e) => { setMinVolume(e.target.value); setPage(0); }}
              />
            </Grid>

            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Max Volume"
                placeholder="1000000000"
                value={maxVolume}
                onChange={(e) => { setMaxVolume(e.target.value); setPage(0); }}
              />
            </Grid>

            {/* RSI Range */}
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Min RSI"
                placeholder="0"
                value={minRsi}
                onChange={(e) => { setMinRsi(e.target.value); setPage(0); }}
                inputProps={{ min: 0, max: 100 }}
              />
            </Grid>

            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Max RSI"
                placeholder="100"
                value={maxRsi}
                onChange={(e) => { setMaxRsi(e.target.value); setPage(0); }}
                inputProps={{ min: 0, max: 100 }}
              />
            </Grid>

            {/* ADX */}
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="number"
                label="Min ADX"
                placeholder="0"
                value={minAdx}
                onChange={(e) => { setMinAdx(e.target.value); setPage(0); }}
              />
            </Grid>

            {/* Clear Button */}
            <Grid item xs={12}>
              <Button
                variant="outlined"
                startIcon={<Clear />}
                onClick={handleClearFilters}
              >
                Clear All Filters
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Content */}
      <ErrorBoundary>
        {isLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress />
          </Box>
        )}

        {isError && (
          <ErrorDisplay
            error={error?.message || "Failed to load signals"}
            retry={() => window.location.reload()}
          />
        )}

        {!isLoading && !isError && filteredSignals.length === 0 && (
          <Box sx={{ p: 4, textAlign: "center" }}>
            <Typography color="text.secondary">
              No signals found for the selected filters. Try adjusting your search or time period.
            </Typography>
          </Box>
        )}

        {!isLoading && !isError && filteredSignals.length > 0 && (
          <Box>
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="body2" color="text.secondary">
                  Showing {filteredSignals.length} of {signalsData?.pagination?.total || 0} signals
                </Typography>
              </CardContent>
            </Card>

            <SignalCardAccordion signals={filteredSignals.slice(0, rowsPerPage)} />
          </Box>
        )}
      </ErrorBoundary>
    </Container>
  );
}

function TradingSignalsWithErrorBoundary() {
  return (
    <ErrorBoundary>
      <TradingSignals />
    </ErrorBoundary>
  );
}

export default TradingSignalsWithErrorBoundary;
