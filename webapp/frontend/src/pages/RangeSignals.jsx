import React, { useState, useEffect } from "react";
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
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  NewReleases,
  FilterList,
  Close,
  Timeline,
  Search,
  Clear,
  HorizontalRule,
} from "@mui/icons-material";
import { formatCurrency, formatPercentage } from "../utils/formatters";
import { formatCellValue, getCellAlign, getDynamicColumns } from "../utils/signalTableHelpers";
import api, { getApiConfig, extractResponseData } from "../services/api";
import { ErrorDisplay, LoadingDisplay } from "../components/ui/ErrorBoundary";
import ErrorBoundary from "../components/ErrorBoundary";
import SignalCardAccordion from "../components/SignalCardAccordion";

const logger = {
  info: (msg) => console.log(`[RangeSignals] ${msg}`),
  error: (msg) => console.error(`[RangeSignals] ${msg}`),
  warn: (msg) => console.warn(`[RangeSignals] ${msg}`),
};

function RangeSignals() {
  useDocumentTitle("Range Trading Signals");
  const theme = useTheme();
  const { apiUrl: API_BASE } = getApiConfig();

  const [signalType, setSignalType] = useState("all");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [historicalDialogOpen, setHistoricalDialogOpen] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [days, setDays] = useState(30);

  const { data: signalsData, isLoading, isError, error } = useQuery({
    queryKey: ["rangeSignals", signalType, days, page],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (signalType !== "all") params.append("signal", signalType);
      params.append("days", days);
      params.append("limit", 500);
      params.append("offset", page * 500);

      const response = await api.get(`/api/signals/range?${params}`);
      return extractResponseData(response);
    },
  });

  const filteredSignals = signalsData?.items?.filter(
    (signal) => !symbolFilter || signal.symbol?.toUpperCase().includes(symbolFilter.toUpperCase())
  ) || [];

  const handleSignalTypeChange = (e) => {
    setSignalType(e.target.value);
    setPage(0);
  };

  const handleDaysChange = (e) => {
    setDays(e.target.value);
    setPage(0);
  };

  const handleSearch = () => {
    setSymbolFilter(searchInput);
    setPage(0);
  };

  const handleClearFilters = () => {
    setSymbolFilter("");
    setSearchInput("");
    setSignalType("all");
    setDays(30);
    setPage(0);
  };

  const getSignalColor = (signal) => {
    if (signal === "BUY") return theme.palette.success.main;
    if (signal === "SELL") return theme.palette.error.main;
    return theme.palette.warning.main;
  };

  const getSignalChip = (signal) => {
    const isBuy = signal === "BUY";
    const isSell = signal === "SELL";

    return (
      <Chip
        label={signal || "HOLD"}
        size="medium"
        icon={
          isBuy ? (
            <TrendingUp />
          ) : isSell ? (
            <TrendingDown />
          ) : (
            <HorizontalRule />
          )
        }
        sx={{
          backgroundColor: theme.palette.action.hover,
          color: theme.palette.text.primary,
          fontWeight: "500",
          fontSize: "0.875rem",
          minWidth: "80px",
          borderRadius: "4px",
        }}
      />
    );
  };

  const RangeSignalsTable = () => {
    const columns = getDynamicColumns(filteredSignals);

    const totalSignals = signalsData?.pagination?.total || filteredSignals?.length || 0;
    const paginatedSignals = filteredSignals?.slice(0, rowsPerPage) || [];

    const displayStart = page * rowsPerPage + 1;
    const displayEnd = displayStart + paginatedSignals.length - 1;

    return (
      <Box>
        <TableContainer component={Paper} elevation={0} sx={{ overflowX: "auto" }}>
          <Table stickyHeader>
            <TableHead>
              <TableRow>
                {columns.map((col) => (
                  <TableCell
                    key={col}
                    align={getCellAlign(col)}
                    sx={{
                      fontWeight: "bold",
                      whiteSpace: "nowrap",
                      minWidth: "100px",
                    }}
                  >
                    <Tooltip title={col} placement="top">
                      <span>{col.replace(/_/g, " ").replace(/^./, str => str.toUpperCase())}</span>
                    </Tooltip>
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {paginatedSignals?.map((signal, index) => (
                <TableRow
                  key={`${signal.symbol}-${signal.date}-${index}`}
                  hover
                  sx={{
                    "&:hover": {
                      backgroundColor: "action.hover",
                    },
                  }}
                >
                  {columns.map((col) => {
                    const value = signal[col];
                    const isSymbolColumn = col === "symbol";
                    const isSignalColumn = col === "signal";

                    return (
                      <TableCell
                        key={`${signal.symbol}-${col}`}
                        align={getCellAlign(col)}
                        sx={{ whiteSpace: "nowrap" }}
                      >
                        {isSymbolColumn ? (
                          <Button
                            variant="text"
                            size="small"
                            sx={{ fontWeight: "bold", minWidth: "auto", p: 0.5 }}
                            onClick={() => {
                              setSelectedSymbol(signal.symbol);
                              setHistoricalDialogOpen(true);
                            }}
                          >
                            {value}
                          </Button>
                        ) : isSignalColumn ? (
                          <Box>{getSignalChip(value)}</Box>
                        ) : (
                          <Typography variant="body2">
                            {formatCellValue(value, col)}
                          </Typography>
                        )}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {paginatedSignals?.length === 0 && (
            <Box sx={{ p: 4, textAlign: "center" }}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                No range signals found
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Try adjusting your filters or date range.
              </Typography>
            </Box>
          )}
        </TableContainer>

        {paginatedSignals?.length > 0 && (
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mt: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Showing {displayStart} to {displayEnd} of {totalSignals.toLocaleString()} signals
            </Typography>
            <Box>
              <Button
                disabled={page === 0}
                onClick={() => setPage(p => p - 1)}
              >
                Previous
              </Button>
              <Typography variant="body2" sx={{ display: "inline", mx: 2 }}>
                Page {page + 1}
              </Typography>
              <Button
                disabled={displayEnd >= totalSignals}
                onClick={() => setPage(p => p + 1)}
              >
                Next
              </Button>
            </Box>
          </Box>
        )}
      </Box>
    );
  };

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          <Timeline sx={{ mr: 1, verticalAlign: "middle" }} />
          Range Trading Signals
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Detects tight trading ranges for bounce plays at support/resistance with TD Sequential confirmation
        </Typography>
      </Box>

      <ErrorBoundary fallback={<ErrorDisplay />}>
        {isLoading ? (
          <LoadingDisplay />
        ) : isError ? (
          <ErrorDisplay error={error} />
        ) : (
          <>
            <Paper sx={{ p: 2, mb: 3 }}>
              <Grid container spacing={2} alignItems="flex-end">
                <Grid item xs={12} sm={6} md={3}>
                  <TextField
                    fullWidth
                    size="small"
                    label="Symbol"
                    placeholder="AAPL"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    onKeyPress={(e) => e.key === "Enter" && handleSearch()}
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton size="small" onClick={handleSearch}>
                            <Search />
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Signal Type</InputLabel>
                    <Select
                      value={signalType}
                      label="Signal Type"
                      onChange={handleSignalTypeChange}
                    >
                      <MenuItem value="all">All Signals</MenuItem>
                      <MenuItem value="BUY">Buy Only</MenuItem>
                      <MenuItem value="SELL">Sell Only</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Days</InputLabel>
                    <Select
                      value={days}
                      label="Days"
                      onChange={handleDaysChange}
                    >
                      <MenuItem value={7}>Last 7 Days</MenuItem>
                      <MenuItem value={30}>Last 30 Days</MenuItem>
                      <MenuItem value={90}>Last 90 Days</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Button
                    fullWidth
                    variant="outlined"
                    startIcon={<Clear />}
                    onClick={handleClearFilters}
                  >
                    Clear Filters
                  </Button>
                </Grid>
              </Grid>
            </Paper>

            <SignalCardAccordion signals={filteredSignals.slice(page * rowsPerPage, (page + 1) * rowsPerPage)} />
          </>
        )}
      </ErrorBoundary>
    </Container>
  );
}

export default RangeSignals;
