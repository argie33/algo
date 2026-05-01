import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "@mui/material/styles";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
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
  Stack,
  Alert,
} from "@mui/material";
import {
  FilterList,
  Search,
  Clear,
  ExpandMore,
  TuneOutlined,
  RestartAlt,
} from "@mui/icons-material";
import api, { getApiConfig, extractResponseData } from "../services/api";
import { ErrorDisplay } from "../components/ui/ErrorBoundary";
import ErrorBoundary from "../components/ErrorBoundary";
import SignalCardAccordion from "../components/SignalCardAccordion";

function TradingSignals() {
  useDocumentTitle("Trading Signals - Advanced Filtering");
  const theme = useTheme();

  // Strategy & Pagination
  const [strategy, setStrategy] = useState("swing");
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);

  // Filters
  const [symbolFilter, setSymbolFilter] = useState("");
  const [signalFilter, setSignalFilter] = useState("");
  const [days, setDays] = useState(3650); // Default: ALL TIME
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [minVolume, setMinVolume] = useState("");
  const [maxVolume, setMaxVolume] = useState("");
  const [minRsi, setMinRsi] = useState("");
  const [maxRsi, setMaxRsi] = useState("");
  const [minAdx, setMinAdx] = useState("");
  const [sort, setSort] = useState("date");
  const [sortOrder, setSortOrder] = useState("DESC");

  // Count active filters (3650 = all time default, so don't count it)
  const activeFilterCount = [
    symbolFilter, signalFilter, days !== 3650, minPrice, maxPrice,
    minVolume, maxVolume, minRsi, maxRsi, minAdx
  ].filter(Boolean).length;

  // Strategy config
  const strategyConfig = {
    swing: {
      title: "Swing Trading Signals",
      description: "AI-powered swing trading with market stage analysis, risk/reward ratios, and technical confirmation",
      icon: "📈",
      color: theme.palette.primary.main,
    },
    range: {
      title: "Range Trading Signals",
      description: "Range bounce and breakout signals with support/resistance levels and breakout quality metrics",
      icon: "📊",
      color: theme.palette.info.main,
    },
    "mean-reversion": {
      title: "Mean Reversion Signals",
      description: "Connors RSI(2) oversold signals with confluence analysis and mean reversion probability",
      icon: "🔄",
      color: theme.palette.success.main,
    },
  };

  const config = strategyConfig[strategy];

  // API Query
  const { data: signalsData, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["signals", strategy, symbolFilter, signalFilter, days, minPrice, maxPrice, minVolume, maxVolume, minRsi, maxRsi, minAdx, sort, sortOrder, page, limit],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append("type", strategy);
      if (symbolFilter) params.append("symbol", symbolFilter.toUpperCase());
      if (signalFilter) params.append("signal", signalFilter);
      params.append("days", days);
      if (minPrice) params.append("min_price", minPrice);
      if (maxPrice) params.append("max_price", maxPrice);
      if (minVolume) params.append("min_volume", minVolume);
      if (maxVolume) params.append("max_volume", maxVolume);
      if (minRsi) params.append("min_rsi", minRsi);
      if (maxRsi) params.append("max_rsi", maxRsi);
      if (minAdx) params.append("min_adx", minAdx);
      params.append("limit", limit);
      params.append("page", page);
      params.append("sort", sort);
      params.append("sort_order", sortOrder);

      const response = await api.get(`/api/signals/search?${params}`);
      return extractResponseData(response);
    },
  });

  const signals = signalsData?.items || [];
  const pagination = signalsData?.pagination || {};

  // Handlers
  const handleClearAll = () => {
    setSymbolFilter("");
    setSignalFilter("");
    setDays(3650); // All time
    setMinPrice("");
    setMaxPrice("");
    setMinVolume("");
    setMaxVolume("");
    setMinRsi("");
    setMaxRsi("");
    setMinAdx("");
    setSort("date");
    setSortOrder("DESC");
    setPage(1);
  };

  const handleRemoveFilter = (type) => {
    const handlers = {
      symbol: () => setSymbolFilter(""),
      signal: () => setSignalFilter(""),
      days: () => setDays(3650), // All time
      minPrice: () => setMinPrice(""),
      maxPrice: () => setMaxPrice(""),
      minRsi: () => setMinRsi(""),
      maxRsi: () => setMaxRsi(""),
      minAdx: () => setMinAdx(""),
    };
    handlers[type]?.();
    setPage(1);
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
          Trading Signals Dashboard
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Advanced filtering across 1M+ signals • All strategies • Historical & current data
        </Typography>
      </Box>

      {/* Strategy Tabs */}
      <Paper sx={{ mb: 4 }}>
        <Tabs value={strategy} onChange={(e, v) => { setStrategy(v); setPage(1); }} variant="fullWidth">
          <Tab label={`${strategyConfig.swing.icon} Swing Trading`} value="swing" />
          <Tab label={`${strategyConfig.range.icon} Range Trading`} value="range" />
          <Tab label={`${strategyConfig["mean-reversion"].icon} Mean Reversion`} value="mean-reversion" />
        </Tabs>
        <Box sx={{ p: 2.5, backgroundColor: `${config.color}12`, borderTop: `2px solid ${config.color}` }}>
          <Typography variant="h6" sx={{ color: config.color, fontWeight: 700, mb: 0.5 }}>
            {config.title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {config.description}
          </Typography>
        </Box>
      </Paper>

      {/* Active Filters Chips */}
      {activeFilterCount > 0 && (
        <Card sx={{ mb: 3, backgroundColor: theme.palette.action.hover }}>
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5 }}>
              <TuneOutlined fontSize="small" color="primary" />
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                {activeFilterCount} Active Filter{activeFilterCount !== 1 ? 's' : ''}
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
              {symbolFilter && <Chip label={`Symbol: ${symbolFilter}`} onDelete={() => handleRemoveFilter("symbol")} color="primary" variant="outlined" size="small" />}
              {signalFilter && <Chip label={`Signal: ${signalFilter}`} onDelete={() => handleRemoveFilter("signal")} color="primary" variant="outlined" size="small" />}
              {days !== 3650 && <Chip label={`${days}d`} onDelete={() => handleRemoveFilter("days")} color="primary" variant="outlined" size="small" />}
              {minPrice && <Chip label={`Min: $${minPrice}`} onDelete={() => handleRemoveFilter("minPrice")} color="primary" variant="outlined" size="small" />}
              {maxPrice && <Chip label={`Max: $${maxPrice}`} onDelete={() => handleRemoveFilter("maxPrice")} color="primary" variant="outlined" size="small" />}
              {minRsi && <Chip label={`RSI ≥ ${minRsi}`} onDelete={() => handleRemoveFilter("minRsi")} color="primary" variant="outlined" size="small" />}
              {maxRsi && <Chip label={`RSI ≤ ${maxRsi}`} onDelete={() => handleRemoveFilter("maxRsi")} color="primary" variant="outlined" size="small" />}
              {minAdx && <Chip label={`ADX ≥ ${minAdx}`} onDelete={() => handleRemoveFilter("minAdx")} color="primary" variant="outlined" size="small" />}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Filter Panel - Accordion */}
      <Card sx={{ mb: 4 }}>
        <Accordion defaultExpanded>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <FilterList sx={{ mr: 1.5 }} />
            <Typography sx={{ fontWeight: 600, flex: 1 }}>Advanced Filters</Typography>
            {activeFilterCount > 0 && <Chip label={activeFilterCount} size="small" color="primary" />}
          </AccordionSummary>
          <Divider />
          <AccordionDetails sx={{ pt: 3, pb: 3 }}>
            <Grid container spacing={2.5}>
              {/* Quick Filters */}
              <Grid item xs={12} sm={6} md={3}>
                <TextField fullWidth label="Symbol" placeholder="AAPL" value={symbolFilter} onChange={(e) => { setSymbolFilter(e.target.value); setPage(1); }} size="small" InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Signal</InputLabel>
                  <Select value={signalFilter} onChange={(e) => { setSignalFilter(e.target.value); setPage(1); }} label="Signal">
                    <MenuItem value="">All</MenuItem>
                    <MenuItem value="BUY">📈 BUY</MenuItem>
                    <MenuItem value="SELL">📉 SELL</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Period</InputLabel>
                  <Select value={days} onChange={(e) => { setDays(e.target.value); setPage(1); }} label="Period">
                    <MenuItem value={7}>7 days</MenuItem>
                    <MenuItem value={30}>30 days</MenuItem>
                    <MenuItem value={90}>90 days</MenuItem>
                    <MenuItem value={180}>6 months</MenuItem>
                    <MenuItem value={365}>1 year</MenuItem>
                    <MenuItem value={3650}>All time</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Per Page</InputLabel>
                  <Select value={limit} onChange={(e) => { setLimit(e.target.value); setPage(1); }} label="Per Page">
                    <MenuItem value={25}>25</MenuItem>
                    <MenuItem value={50}>50</MenuItem>
                    <MenuItem value={100}>100</MenuItem>
                    <MenuItem value={250}>250</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* Price Section */}
              <Grid item xs={12}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: theme.palette.text.secondary }}>Price Range</Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TextField fullWidth type="number" label="Min" placeholder="0" value={minPrice} onChange={(e) => { setMinPrice(e.target.value); setPage(1); }} size="small" inputProps={{ step: "0.01" }} />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TextField fullWidth type="number" label="Max" placeholder="10000" value={maxPrice} onChange={(e) => { setMaxPrice(e.target.value); setPage(1); }} size="small" inputProps={{ step: "0.01" }} />
              </Grid>

              {/* Volume Section */}
              <Grid item xs={12} sm={6} md={2}>
                <TextField fullWidth type="number" label="Min Vol" placeholder="0" value={minVolume} onChange={(e) => { setMinVolume(e.target.value); setPage(1); }} size="small" />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TextField fullWidth type="number" label="Max Vol" placeholder="∞" value={maxVolume} onChange={(e) => { setMaxVolume(e.target.value); setPage(1); }} size="small" />
              </Grid>

              {/* Technical Section */}
              <Grid item xs={12}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: theme.palette.text.secondary }}>Technical Indicators</Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TextField fullWidth type="number" label="Min RSI" placeholder="0" value={minRsi} onChange={(e) => { setMinRsi(e.target.value); setPage(1); }} size="small" inputProps={{ min: 0, max: 100 }} />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TextField fullWidth type="number" label="Max RSI" placeholder="100" value={maxRsi} onChange={(e) => { setMaxRsi(e.target.value); setPage(1); }} size="small" inputProps={{ min: 0, max: 100 }} />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TextField fullWidth type="number" label="Min ADX" placeholder="0" value={minAdx} onChange={(e) => { setMinAdx(e.target.value); setPage(1); }} size="small" />
              </Grid>

              {/* Sorting Section */}
              <Grid item xs={12}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: theme.palette.text.secondary }}>Sorting</Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Sort By</InputLabel>
                  <Select value={sort} onChange={(e) => { setSort(e.target.value); setPage(1); }} label="Sort By">
                    <MenuItem value="date">📅 Date</MenuItem>
                    <MenuItem value="symbol">🏷️ Symbol</MenuItem>
                    <MenuItem value="close">💰 Price</MenuItem>
                    <MenuItem value="volume">📊 Volume</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Order</InputLabel>
                  <Select value={sortOrder} onChange={(e) => { setSortOrder(e.target.value); setPage(1); }} label="Order">
                    <MenuItem value="DESC">Newest ↓</MenuItem>
                    <MenuItem value="ASC">Oldest ↑</MenuItem>
                  </Select>
                </FormControl>
              </Grid>

              {/* Buttons */}
              <Grid item xs={12}>
                <Box sx={{ display: "flex", gap: 1.5 }}>
                  <Button variant="contained" onClick={() => refetch()} sx={{ fontWeight: 600 }}>
                    Apply Filters
                  </Button>
                  {activeFilterCount > 0 && (
                    <Button variant="outlined" startIcon={<RestartAlt />} onClick={handleClearAll} sx={{ fontWeight: 600 }}>
                      Reset ({activeFilterCount})
                    </Button>
                  )}
                </Box>
              </Grid>
            </Grid>
          </AccordionDetails>
        </Accordion>
      </Card>

      {/* Results */}
      <ErrorBoundary>
        {isLoading && <Box sx={{ textAlign: "center", py: 6 }}><CircularProgress /></Box>}

        {isError && <ErrorDisplay error={error?.message || "Failed to load signals"} retry={() => refetch()} />}

        {!isLoading && !isError && signals.length === 0 && (
          <Card sx={{ p: 4, textAlign: "center" }}>
            <Typography variant="h6" color="text.secondary" gutterBottom>No Signals Found</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Try adjusting filters or expanding time period</Typography>
            <Button variant="outlined" onClick={handleClearAll} startIcon={<RestartAlt />}>Reset Filters</Button>
          </Card>
        )}

        {!isLoading && !isError && signals.length > 0 && (
          <Box>
            <Card sx={{ mb: 3, backgroundColor: theme.palette.action.hover }}>
              <CardContent sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Showing {signals.length} of {pagination.total?.toLocaleString() || 0} signals
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Page {pagination.page} of {pagination.totalPages}
                  </Typography>
                </Box>
                <Chip label={strategy.toUpperCase()} color="primary" />
              </CardContent>
            </Card>

            <SignalCardAccordion signals={signals} />

            {pagination.totalPages > 1 && (
              <Box sx={{ display: "flex", justifyContent: "center", gap: 1, mt: 4 }}>
                <Button disabled={page === 1} onClick={() => setPage(page - 1)} variant="outlined">← Prev</Button>
                <Typography sx={{ display: "flex", alignItems: "center", px: 2 }}>Page {page}/{pagination.totalPages}</Typography>
                <Button disabled={page === pagination.totalPages} onClick={() => setPage(page + 1)} variant="outlined">Next →</Button>
              </Box>
            )}
          </Box>
        )}
      </ErrorBoundary>
    </Container>
  );
}

export default function TradingSignalsPage() {
  return <ErrorBoundary><TradingSignals /></ErrorBoundary>;
}
