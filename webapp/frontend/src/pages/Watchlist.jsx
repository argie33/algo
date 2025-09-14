import { useState, useEffect } from "react";
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Button,
  TextField,
  Chip,
  Alert,
  LinearProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from "@mui/material";
import {
  Add,
  Delete,
  Refresh,
  TrendingUp,
  TrendingDown,
} from "@mui/icons-material";
import { useAuth } from "../contexts/AuthContext";
import api from "../services/api";
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
} from "../utils/formatters";

const Watchlist = () => {
  const { user } = useAuth();
  const [watchlist, setWatchlist] = useState([]);
  const [marketData, setMarketData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");
  const [lastUpdate, setLastUpdate] = useState(new Date());

  const loadWatchlist = async () => {
    try {
      // For now, use a default watchlist stored locally
      // In a full implementation, this would come from user preferences/database
      const defaultWatchlist = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "TSLA",
        "NVDA",
        "META",
      ];
      setWatchlist(defaultWatchlist);
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV) console.error("Failed to load watchlist:", error);
      setError("Failed to load watchlist");
    }
  };

  const loadMarketData = async (symbols) => {
    try {
      setError(null);
      
      // Use passed symbols or fallback to current watchlist
      const symbolsToLoad = symbols || watchlist;

      if (!user || (symbolsToLoad?.length || 0) === 0) {
        return;
      }

      console.log(`Loading market data for ${(symbolsToLoad?.length || 0)} symbols`);

      const response = await api.get(
        `/api/websocket/stream/${symbolsToLoad.join(",")}`
      );

      if (response?.data.success) {
        const liveData = response?.data.data;

        // Transform API data for display
        const transformedData = {};
        for (const symbol of symbolsToLoad) {
          const symbolData = liveData?.data && liveData.data[symbol];
          if (symbolData && !symbolData.error) {
            const midPrice = (symbolData.bidPrice + symbolData.askPrice) / 2;
            transformedData[symbol] = {
              symbol: symbol,
              price: midPrice,
              bidPrice: symbolData.bidPrice,
              askPrice: symbolData.askPrice,
              spread: symbolData.askPrice - symbolData.bidPrice,
              spreadPercent:
                ((symbolData.askPrice - symbolData.bidPrice) / midPrice) * 100,
              volume: symbolData.bidSize + symbolData.askSize,
              timestamp: symbolData.timestamp,
              dataSource: "live",
              // Real change data would need historical comparison - set to 0 for now
              change: 0,
              changePercent: 0,
            };
          } else {
            transformedData[symbol] = {
              symbol: symbol,
              price: 0,
              error: symbolData?.error || "Data unavailable",
              dataSource: "error",
            };
          }
        }

        setMarketData(transformedData);
        setLastUpdate(new Date());

        console.log("✅ Watchlist market data loaded successfully", {
          symbols: (symbolsToLoad?.length || 0),
          successful: Object.values(transformedData).filter((d) => !d.error)
            .length,
          failed: Object.values(transformedData).filter((d) => d.error).length,
        });
      } else {
        throw new Error("Failed to fetch watchlist market data");
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV) console.error("Failed to load market data:", error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

  // Initialize watchlist on component mount
  useEffect(() => {
    loadWatchlist();
  }, []);

  // Load market data when watchlist changes
  useEffect(() => {
    if (watchlist.length > 0) {
      loadMarketData(watchlist);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchlist]);

  const addSymbol = () => {
    const symbol = newSymbol.toUpperCase().trim();
    if (symbol && !watchlist.includes(symbol) && /^[A-Z]+$/.test(symbol)) {
      setWatchlist([...watchlist, symbol]);
      setNewSymbol("");
      setAddDialogOpen(false);
    }
  };

  const removeSymbol = (symbol) => {
    setWatchlist(watchlist.filter((s) => s !== symbol));
    const newMarketData = { ...marketData };
    delete newMarketData[symbol];
    setMarketData(newMarketData);
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
            Watchlist
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Track your favorite stocks with real-time market data
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip
              label={`${(watchlist?.length || 0)} symbols`}
              color="primary"
              size="small"
            />
            <Chip
              label="Live Data"
              color="success"
              size="small"
              variant="outlined"
            />
            <Chip
              label={`Updated ${formatTimeAgo(lastUpdate)}`}
              color="primary"
              size="small"
              variant="filled"
            />
          </Box>
        </Box>

        <Box display="flex" gap={2}>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAddDialogOpen(true)}
          >
            Add Symbol
          </Button>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => loadMarketData(watchlist)}
            disabled={loading}
          >
            Refresh
          </Button>
        </Box>
      </Box>

      {/* Loading State */}
      {loading && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} py={2}>
              <LinearProgress sx={{ flexGrow: 1 }} />
              <Typography>Loading watchlist data...</Typography>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Error State */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Failed to Load Watchlist Data
          </Typography>
          <Typography variant="body2">{error}</Typography>
          <Button
            variant="outlined"
            size="small"
            onClick={() => loadMarketData(watchlist)}
            sx={{ mt: 1 }}
          >
            Retry
          </Button>
        </Alert>
      )}

      {/* Watchlist Table */}
      {!loading && watchlist.length > 0 && (
        <Card>
          <CardContent>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>
                      <strong>Symbol</strong>
                    </TableCell>
                    <TableCell align="right">
                      <strong>Price</strong>
                    </TableCell>
                    <TableCell align="right">
                      <strong>Change</strong>
                    </TableCell>
                    <TableCell align="right">
                      <strong>Change %</strong>
                    </TableCell>
                    <TableCell align="right">
                      <strong>Bid/Ask</strong>
                    </TableCell>
                    <TableCell align="right">
                      <strong>Spread</strong>
                    </TableCell>
                    <TableCell align="right">
                      <strong>Volume</strong>
                    </TableCell>
                    <TableCell align="center">
                      <strong>Actions</strong>
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(watchlist || []).map((symbol) => {
                    const data = marketData[symbol] || {};
                    const hasError = data.error;
                    const isPositive = data.change >= 0;

                    return (
                      <TableRow key={symbol} hover>
                        <TableCell>
                          <Box display="flex" alignItems="center" gap={1}>
                            <Typography variant="h6" fontWeight="bold">
                              {symbol}
                            </Typography>
                            {hasError && (
                              <Chip label="Error" color="error" size="small" />
                            )}
                          </Box>
                        </TableCell>

                        <TableCell align="right">
                          {hasError ? (
                            <Typography color="error">--</Typography>
                          ) : (
                            <Typography variant="h6" fontWeight="bold">
                              {formatCurrency(data.price)}
                            </Typography>
                          )}
                        </TableCell>

                        <TableCell align="right">
                          {hasError ? (
                            <Typography color="error">--</Typography>
                          ) : (
                            <Box
                              display="flex"
                              alignItems="center"
                              justifyContent="flex-end"
                              gap={1}
                            >
                              {isPositive ? (
                                <TrendingUp color="success" fontSize="small" />
                              ) : (
                                <TrendingDown color="error" fontSize="small" />
                              )}
                              <Typography
                                color={
                                  isPositive ? "success.main" : "error.main"
                                }
                                fontWeight="bold"
                              >
                                {formatCurrency(Math.abs(data.change))}
                              </Typography>
                            </Box>
                          )}
                        </TableCell>

                        <TableCell align="right">
                          {hasError ? (
                            <Typography color="error">--</Typography>
                          ) : (
                            <Typography
                              color={isPositive ? "success.main" : "error.main"}
                              fontWeight="bold"
                            >
                              {formatPercentage(Math.abs(data.changePercent))}
                            </Typography>
                          )}
                        </TableCell>

                        <TableCell align="right">
                          {hasError ? (
                            <Typography color="error">--</Typography>
                          ) : (
                            <Box>
                              <Typography variant="body2">
                                {formatCurrency(data.bidPrice)} /{" "}
                                {formatCurrency(data.askPrice)}
                              </Typography>
                            </Box>
                          )}
                        </TableCell>

                        <TableCell align="right">
                          {hasError ? (
                            <Typography color="error">--</Typography>
                          ) : (
                            <Box>
                              <Typography variant="body2">
                                {formatCurrency(data.spread)}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                ({formatPercentage(data.spreadPercent)})
                              </Typography>
                            </Box>
                          )}
                        </TableCell>

                        <TableCell align="right">
                          {hasError ? (
                            <Typography color="error">--</Typography>
                          ) : (
                            <Typography variant="body2">
                              {formatNumber(data.volume)}
                            </Typography>
                          )}
                        </TableCell>

                        <TableCell align="center">
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => removeSymbol(symbol)}
                            aria-label={`Remove ${symbol} from watchlist`}
                          >
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {!loading && (watchlist?.length || 0) === 0 && (
        <Card>
          <CardContent sx={{ textAlign: "center", py: 6 }}>
            <Typography variant="h5" gutterBottom color="text.secondary">
              Your watchlist is empty
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
              Add some symbols to start tracking your favorite stocks
            </Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setAddDialogOpen(true)}
            >
              Add Your First Symbol
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Add Symbol Dialog */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)}>
        <DialogTitle>Add Symbol to Watchlist</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Stock Symbol"
            type="text"
            fullWidth
            variant="outlined"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            placeholder="e.g. AAPL, MSFT, GOOGL"
            helperText="Enter a valid stock symbol (letters only)"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)}>Cancel</Button>
          <Button
            onClick={addSymbol}
            variant="contained"
            disabled={!newSymbol.trim() || !/^[A-Z]+$/.test(newSymbol.trim())}
          >
            Add Symbol
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default Watchlist;
