import { useState, useEffect } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  Alert,
  useTheme,
  alpha,
  Tooltip,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  Public,
  FilterList,
  ClearAll,
} from "@mui/icons-material";

// Trading Signal Component
const TradingSignal = ({ signal, size = "small" }) => {
  const theme = useTheme();

  const getSignalConfig = (signalType) => {
    switch (signalType?.toUpperCase()) {
      case "BUY":
        return {
          color: theme.palette.success.main,
          bgColor: alpha(theme.palette.success.main, 0.1),
          icon: <TrendingUp sx={{ fontSize: size === "small" ? 16 : 20 }} />,
          label: "BUY",
        };
      case "SELL":
        return {
          color: theme.palette.error.main,
          bgColor: alpha(theme.palette.error.main, 0.1),
          icon: <TrendingDown sx={{ fontSize: size === "small" ? 16 : 20 }} />,
          label: "SELL",
        };
      case "HOLD":
        return {
          color: theme.palette.warning.main,
          bgColor: alpha(theme.palette.warning.main, 0.1),
          icon: <ShowChart sx={{ fontSize: size === "small" ? 16 : 20 }} />,
          label: "HOLD",
        };
      default:
        return {
          color: theme.palette.grey[500],
          bgColor: alpha(theme.palette.grey[500], 0.1),
          icon: <ShowChart sx={{ fontSize: size === "small" ? 16 : 20 }} />,
          label: signal || "NEUTRAL",
        };
    }
  };

  const config = getSignalConfig(signal);

  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 1.5,
        py: 0.5,
        borderRadius: 1,
        backgroundColor: config.bgColor,
        color: config.color,
        fontWeight: 600,
        fontSize: size === "small" ? "0.75rem" : "0.875rem",
      }}
    >
      {config.icon}
      {config.label}
    </Box>
  );
};

export default function WorldETFsDashboard() {
  const theme = useTheme();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [etfList, setEtfList] = useState([]);
  const [prices, setPrices] = useState({});
  const [signals, setSignals] = useState({});
  const [selectedRegion, setSelectedRegion] = useState("all");
  const [selectedTimeframe, setSelectedTimeframe] = useState("daily");
  const [searchSymbol, setSearchSymbol] = useState("");
  const [regions, setRegions] = useState([]);

  // Fetch ETF list
  const fetchETFList = async () => {
    try {
      const response = await fetch("/api/world-etfs/list");
      if (!response.ok) throw new Error("Failed to fetch ETF list");
      const result = await response.json();
      if (result.success && result.data) {
        setEtfList(result.data.all_etfs || []);
        setRegions(result.data.regions || []);
      }
    } catch (err) {
      console.error("Error fetching ETF list:", err);
      setError("Failed to load world ETF list");
    }
  };

  // Fetch prices for visible ETFs
  const fetchPrices = async (symbols) => {
    if (!symbols || symbols.length === 0) return;
    try {
      const querySymbols = symbols.slice(0, 50).map(s => s.symbol || s).join(",");
      const response = await fetch(
        `/api/world-etfs/prices?symbols=${querySymbols}&timeframe=${selectedTimeframe}&limit=200`
      );
      if (!response.ok) throw new Error("Failed to fetch prices");
      const result = await response.json();
      if (result.success) {
        setPrices(result.data.prices_by_symbol || {});
      }
    } catch (err) {
      console.error("Error fetching prices:", err);
    }
  };

  // Fetch signals for visible ETFs
  const fetchSignals = async (symbols) => {
    if (!symbols || symbols.length === 0) return;
    try {
      const querySymbols = symbols.slice(0, 50).map(s => s.symbol || s).join(",");
      const response = await fetch(
        `/api/world-etfs/signals?symbols=${querySymbols}&timeframe=${selectedTimeframe}&limit=200`
      );
      if (!response.ok) throw new Error("Failed to fetch signals");
      const result = await response.json();
      if (result.success) {
        setSignals(result.data.signals_by_symbol || {});
      }
    } catch (err) {
      console.error("Error fetching signals:", err);
    }
  };

  // Initial load
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchETFList();
      setLoading(false);
    };
    load();
  }, []);

  // Fetch data when region or timeframe changes
  useEffect(() => {
    if (etfList.length === 0) return;

    const filtered = selectedRegion === "all"
      ? etfList
      : etfList.filter(e => e.country_region === selectedRegion);

    fetchPrices(filtered);
    fetchSignals(filtered);
  }, [selectedRegion, selectedTimeframe, etfList]);

  // Filter ETFs based on region and search
  const filteredETFs = etfList
    .filter(etf =>
      selectedRegion === "all" || etf.country_region === selectedRegion
    )
    .filter(etf =>
      searchSymbol === "" ||
      etf.symbol.toLowerCase().includes(searchSymbol.toLowerCase()) ||
      (etf.name && etf.name.toLowerCase().includes(searchSymbol.toLowerCase()))
    );

  const getLatestPrice = (symbol) => {
    const priceData = prices[symbol];
    if (!priceData || priceData.length === 0) return null;
    return priceData[0];
  };

  const getLatestSignal = (symbol) => {
    const signalData = signals[symbol];
    if (!signalData || signalData.length === 0) return null;
    return signalData[0];
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "400px" }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2 }}>
          <Public sx={{ fontSize: 32, color: theme.palette.primary.main }} />
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700 }}>
              World ETFs Dashboard
            </Typography>
            <Typography variant="body2" color="textSecondary">
              Country and region-specific ETF analysis with buy/sell signals
            </Typography>
          </Box>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Controls */}
      <Paper sx={{ p: 3, mb: 3, backgroundColor: alpha(theme.palette.primary.main, 0.02) }}>
        <Grid container spacing={3}>
          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth>
              <InputLabel>Region</InputLabel>
              <Select
                value={selectedRegion}
                label="Region"
                onChange={(e) => setSelectedRegion(e.target.value)}
              >
                <MenuItem value="all">All Regions</MenuItem>
                {regions.map(region => (
                  <MenuItem key={region} value={region}>
                    {region}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth>
              <InputLabel>Timeframe</InputLabel>
              <Select
                value={selectedTimeframe}
                label="Timeframe"
                onChange={(e) => setSelectedTimeframe(e.target.value)}
              >
                <MenuItem value="daily">Daily</MenuItem>
                <MenuItem value="weekly">Weekly</MenuItem>
                <MenuItem value="monthly">Monthly</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={12} md={6}>
            <TextField
              fullWidth
              placeholder="Search by symbol or name..."
              value={searchSymbol}
              onChange={(e) => setSearchSymbol(e.target.value)}
              InputProps={{
                startAdornment: <FilterList sx={{ mr: 1, color: "action.active" }} />,
              }}
            />
          </Grid>
        </Grid>

        {searchSymbol && (
          <Box sx={{ mt: 2, display: "flex", gap: 1 }}>
            <Typography variant="body2" color="textSecondary">
              Found {filteredETFs.length} ETF(s)
            </Typography>
            <Button
              size="small"
              startIcon={<ClearAll />}
              onClick={() => setSearchSymbol("")}
            >
              Clear
            </Button>
          </Box>
        )}
      </Paper>

      {/* ETF Table */}
      <Card>
        <TableContainer>
          <Table>
            <TableHead sx={{ backgroundColor: alpha(theme.palette.primary.main, 0.08) }}>
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>Symbol</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Name</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Region</TableCell>
                <TableCell sx={{ fontWeight: 700 }}>Category</TableCell>
                <TableCell sx={{ fontWeight: 700 }} align="right">
                  Price
                </TableCell>
                <TableCell sx={{ fontWeight: 700 }} align="right">
                  Signal
                </TableCell>
                <TableCell sx={{ fontWeight: 700 }} align="right">
                  Strength
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredETFs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <Typography color="textSecondary">
                      No ETFs found for selected filters
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                filteredETFs.map((etf) => {
                  const latestPrice = getLatestPrice(etf.symbol);
                  const latestSignal = getLatestSignal(etf.symbol);

                  return (
                    <TableRow key={etf.symbol} hover>
                      <TableCell>
                        <Tooltip title={etf.symbol}>
                          <Chip
                            label={etf.symbol}
                            variant="outlined"
                            size="small"
                          />
                        </Tooltip>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {etf.name || "-"}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={etf.country_region}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="textSecondary">
                          {etf.category || "-"}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        {latestPrice ? (
                          <Box>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              ${latestPrice.close?.toFixed(2) || "-"}
                            </Typography>
                            <Typography variant="caption" color="textSecondary">
                              {latestPrice.date}
                            </Typography>
                          </Box>
                        ) : (
                          <Typography variant="body2" color="textSecondary">
                            -
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell align="right">
                        {latestSignal ? (
                          <TradingSignal signal={latestSignal.signal} />
                        ) : (
                          <Typography variant="body2" color="textSecondary">
                            -
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell align="right">
                        {latestSignal && latestSignal.strength ? (
                          <Tooltip title={`Signal Strength: ${(latestSignal.strength * 100).toFixed(1)}%`}>
                            <Chip
                              label={`${(latestSignal.strength * 100).toFixed(0)}%`}
                              size="small"
                              color={
                                latestSignal.strength >= 0.7
                                  ? "success"
                                  : latestSignal.strength >= 0.4
                                  ? "warning"
                                  : "default"
                              }
                              variant="outlined"
                            />
                          </Tooltip>
                        ) : (
                          <Typography variant="body2" color="textSecondary">
                            -
                          </Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </TableContainer>
        <CardContent sx={{ backgroundColor: alpha(theme.palette.primary.main, 0.02), borderTop: `1px solid ${theme.palette.divider}` }}>
          <Typography variant="body2" color="textSecondary">
            Showing {filteredETFs.length} of {etfList.length} total world ETFs
          </Typography>
        </CardContent>
      </Card>

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mt: 2 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Total ETFs
              </Typography>
              <Typography variant="h5">
                {etfList.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Regions
              </Typography>
              <Typography variant="h5">
                {regions.length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                With Price Data
              </Typography>
              <Typography variant="h5">
                {Object.keys(prices).length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                With Signals
              </Typography>
              <Typography variant="h5">
                {Object.keys(signals).length}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
}
