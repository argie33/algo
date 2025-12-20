import React, { useState, useMemo } from "react";
import {
  Box,
  TextField,
  Paper,
  CircularProgress,
  Alert,
  Chip,
  Typography,
  Grid,
  useTheme,
  alpha,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  TableSortLabel,
} from "@mui/material";
import {
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  TrendingFlat as TrendingFlatIcon,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { getApiUrl } from "../../utils/apiUrl";

const API_BASE = getApiUrl();

function CoveredCallOpportunities() {
  const theme = useTheme();
  const [symbolFilter, setSymbolFilter] = useState("");
  const [minProbFilter, setMinProbFilter] = useState("70");
  const [minPremiumFilter, setMinPremiumFilter] = useState("1.5");
  const [sortBy, setSortBy] = useState("premium_pct");
  const [sortOrder, setSortOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(100);

  // Build query parameters
  const queryParams = useMemo(() => {
    const params = new URLSearchParams({
      limit: rowsPerPage,
      page: page + 1,
      sort_by: sortBy,
      min_probability: minProbFilter || 70,
      min_premium_pct: minPremiumFilter || 1.5,
    });

    if (symbolFilter.trim()) {
      params.append("symbol", symbolFilter.trim().toUpperCase());
    }

    return params.toString();
  }, [symbolFilter, minProbFilter, minPremiumFilter, sortBy, page, rowsPerPage]);

  // Fetch opportunities
  const { data, isLoading, error } = useQuery({
    queryKey: ["coveredCalls", queryParams],
    queryFn: async () => {
      // Add cache-busting parameter for fresh data
      const separator = queryParams ? "&" : "?";
      const url = `${API_BASE}/api/strategies/covered-calls?${queryParams}${separator}_t=${Date.now()}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error("Failed to fetch opportunities");
      return response.json();
    },
    refetchOnWindowFocus: true,
    staleTime: 0,
    gcTime: 0,
    cacheTime: 0,
    refetchInterval: 5000,
  });

  const items = data?.items || [];

  // Helpers
  const formatPercent = (value) => (value !== null && value !== undefined ? `${value.toFixed(2)}%` : "—");
  const formatPrice = (value) => (value !== null && value !== undefined ? `$${value.toFixed(2)}` : "—");
  const formatNumber = (value) => (value !== null && value !== undefined ? value.toFixed(2) : "—");

  // Convert database signals to user-friendly sell-side terminology
  const getDisplaySignal = (signal) => {
    if (signal === "STRONG_BUY") return "EXECUTE";
    if (signal === "BUY") return "GOOD";
    if (signal === "WAIT") return "WAIT";
    return "AVOID";
  };

  const getSignalConfig = (signal) => {
    const displaySignal = getDisplaySignal(signal);
    if (displaySignal === "EXECUTE" || displaySignal === "GOOD") {
      return {
        color: theme.palette.success.main,
        textColor: theme.palette.success.dark,
        bgColor: alpha(theme.palette.success.main, 0.1),
        borderColor: alpha(theme.palette.success.main, 0.2),
      };
    } else if (displaySignal === "WAIT") {
      return {
        color: theme.palette.warning.main,
        textColor: theme.palette.warning.dark,
        bgColor: alpha(theme.palette.warning.main, 0.1),
        borderColor: alpha(theme.palette.warning.main, 0.2),
      };
    }
    return {
      color: theme.palette.error.main,
      textColor: theme.palette.error.dark,
      bgColor: alpha(theme.palette.error.main, 0.1),
      borderColor: alpha(theme.palette.error.main, 0.2),
    };
  };

  const getTrendIcon = (trend) => {
    if (trend === "uptrend") return <TrendingUpIcon sx={{ fontSize: 18, color: theme.palette.success.main }} />;
    if (trend === "downtrend") return <TrendingDownIcon sx={{ fontSize: 18, color: theme.palette.error.main }} />;
    return <TrendingFlatIcon sx={{ fontSize: 18, color: theme.palette.warning.main }} />;
  };


  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mb: 2 }}>
        Error loading opportunities: {error.message}
      </Alert>
    );
  }

  return (
    <Box>
      {/* Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Typography variant="h6" sx={{ mb: 2, fontWeight: 700 }}>
          Filters
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={3}>
            <TextField
              label="Stock Symbol"
              value={symbolFilter}
              onChange={(e) => {
                setSymbolFilter(e.target.value);
                setPage(0);
              }}
              placeholder="AAPL or blank for all"
              size="small"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <TextField
              label="Min PoP %"
              type="number"
              value={minProbFilter}
              onChange={(e) => {
                setMinProbFilter(e.target.value);
                setPage(0);
              }}
              size="small"
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <TextField
              label="Min Premium %"
              type="number"
              value={minPremiumFilter}
              onChange={(e) => {
                setMinPremiumFilter(e.target.value);
                setPage(0);
              }}
              size="small"
              fullWidth
            />
          </Grid>
        </Grid>
      </Paper>

      {/* Summary */}
      <Box sx={{ mb: 2, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          Found <strong>{data?.pagination?.total || 0}</strong> opportunities
        </Typography>
      </Box>

      {isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error">Error loading opportunities: {error.message}</Alert>
      ) : items.length === 0 ? (
        <Alert severity="info">No opportunities found with current filters</Alert>
      ) : (
        <TableContainer component={Paper}>
          <Table stickyHeader size="small">
            <TableHead sx={{ backgroundColor: theme.palette.grey[100] }}>
              <TableRow>
                <TableCell sx={{ fontWeight: 700, minWidth: 80 }}>Symbol</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, minWidth: 90 }}>
                  <TableSortLabel
                    active={sortBy === "premium_pct"}
                    direction={sortOrder === "asc" ? "asc" : "desc"}
                    onClick={() => {
                      if (sortBy === "premium_pct") {
                        setSortOrder(sortOrder === "asc" ? "desc" : "asc");
                      } else {
                        setSortBy("premium_pct");
                        setSortOrder("desc");
                      }
                      setPage(0);
                    }}
                  >
                    Premium %
                  </TableSortLabel>
                </TableCell>
                <TableCell align="center" sx={{ fontWeight: 700, minWidth: 70 }}>PoP %</TableCell>
                <TableCell align="center" sx={{ fontWeight: 700, minWidth: 70 }}>Signal</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, minWidth: 85 }}>Annual %</TableCell>
                <TableCell align="center" sx={{ fontWeight: 700, minWidth: 70 }}>Days DTE</TableCell>
                <TableCell align="center" sx={{ fontWeight: 700, minWidth: 70 }}>Trend</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, minWidth: 80 }}>Price</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, minWidth: 80 }}>Strike</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, minWidth: 70 }}>Max Profit</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.map((row) => {
                const config = getSignalConfig(row.entry_signal);
                return (
                  <TableRow key={`${row.symbol}-${row.id}`} hover>
                    <TableCell sx={{ fontWeight: 600 }}>{row.symbol}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600, color: theme.palette.success.main }}>
                      {formatPercent(row.premium_pct)}
                    </TableCell>
                    <TableCell align="center">{row.probability_of_profit}%</TableCell>
                    <TableCell align="center">
                      <Chip
                        label={getDisplaySignal(row.entry_signal)}
                        size="small"
                        sx={{
                          backgroundColor: alpha(config.color, 0.2),
                          color: config.textColor,
                          fontWeight: 600,
                          border: `1px solid ${config.color}`,
                        }}
                      />
                    </TableCell>
                    <TableCell align="right" sx={{ color: theme.palette.success.main }}>
                      {formatPercent(row.expected_annual_return)}
                    </TableCell>
                    <TableCell align="center">{row.days_to_expiration}d</TableCell>
                    <TableCell align="center">{getTrendIcon(row.trend)}</TableCell>
                    <TableCell align="right">${row.stock_price?.toFixed(2)}</TableCell>
                    <TableCell align="right">${row.strike?.toFixed(2)}</TableCell>
                    <TableCell align="right">${row.max_profit?.toFixed(2)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <TablePagination
            rowsPerPageOptions={[50, 100, 250]}
            component="div"
            count={data?.pagination?.total || 0}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={(event, newPage) => setPage(newPage)}
            onRowsPerPageChange={(event) => {
              setRowsPerPage(parseInt(event.target.value, 10));
              setPage(0);
            }}
          />
        </TableContainer>
      )}
    </Box>
  );
}

export default CoveredCallOpportunities;
