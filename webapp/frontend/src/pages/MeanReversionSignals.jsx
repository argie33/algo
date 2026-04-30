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
import MeanReversionAccordion from "../components/MeanReversionAccordion";

const logger = {
  info: (msg) => console.log(`[MeanReversionSignals] ${msg}`),
  error: (msg) => console.error(`[MeanReversionSignals] ${msg}`),
  warn: (msg) => console.warn(`[MeanReversionSignals] ${msg}`),
};

function MeanReversionSignals() {
  useDocumentTitle("Mean Reversion Signals");
  const theme = useTheme();
  const { apiUrl: API_BASE } = getApiConfig();

  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [searchInput, setSearchInput] = useState("");
  const [minConfluence, setMinConfluence] = useState(0);
  const [days, setDays] = useState(30);

  const { data: signalsData, isLoading, isError, error } = useQuery({
    queryKey: ["meanReversionSignals", minConfluence, days, page],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.append("min_confluence", minConfluence);
      params.append("days", days);
      params.append("limit", 500);
      params.append("offset", page * 500);

      const response = await api.get(`/api/signals/mean-reversion?${params}`);
      return extractResponseData(response);
    },
  });

  const filteredSignals = signalsData?.items?.filter(
    (signal) => !searchInput || signal.symbol?.toUpperCase().includes(searchInput.toUpperCase())
  ) || [];

  const handleMinConfluenceChange = (e) => {
    setMinConfluence(e.target.value);
    setPage(0);
  };

  const handleDaysChange = (e) => {
    setDays(e.target.value);
    setPage(0);
  };

  const handleSearch = () => {
    setPage(0);
  };

  const handleClearFilters = () => {
    setSearchInput("");
    setMinConfluence(0);
    setDays(30);
    setPage(0);
  };

  const getConfluenceColor = (score) => {
    if (score >= 4) return theme.palette.success.main;
    if (score >= 2) return theme.palette.warning.main;
    return theme.palette.error.main;
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

  const MeanReversionTable = () => {
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
                    const isConfluenceColumn = col === "confluence_score";

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
                          >
                            {value}
                          </Button>
                        ) : isSignalColumn ? (
                          <Box>{getSignalChip(value)}</Box>
                        ) : isConfluenceColumn ? (
                          <Chip
                            label={value}
                            size="small"
                            sx={{
                              backgroundColor: getConfluenceColor(value) + "20",
                              color: getConfluenceColor(value),
                              fontWeight: "bold",
                              fontSize: "0.75rem",
                            }}
                          />
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
                No mean reversion signals found
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Try adjusting your filters or confluence threshold.
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
          <Analytics sx={{ mr: 1, verticalAlign: "middle" }} />
          Mean Reversion Signals (Connors RSI &lt;10)
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Identifies oversold stocks in uptrends using Connors RSI(2) with DeMark TD Sequential confluence scoring
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
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    label="Min Confluence Score"
                    value={minConfluence}
                    onChange={handleMinConfluenceChange}
                    inputProps={{ min: 0, max: 5 }}
                  />
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

            <MeanReversionAccordion signals={filteredSignals.slice(page * rowsPerPage, (page + 1) * rowsPerPage)} />
          </>
        )}
      </ErrorBoundary>
    </Container>
  );
}

export default MeanReversionSignals;
