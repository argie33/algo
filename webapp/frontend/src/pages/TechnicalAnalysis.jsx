import { useState, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { createComponentLogger } from "../utils/errorLogger";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  CircularProgress,
  Alert,
  TextField,
  Button,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  InputAdornment,
  TablePagination,
  Divider,
} from "@mui/material";
import {
  ExpandMore,
  Search,
  FilterList,
  Clear,
  TrendingUp,
  TrendingDown,
  HorizontalRule,
  ShowChart,
  InfoOutlined,
} from "@mui/icons-material";
import { formatNumber, formatDate, getTechStatus } from "../utils/formatters";
import { getTechnicalData } from "../services/api";
import { useNavigate } from "react-router-dom";

function TechnicalAnalysis() {
  const logger = createComponentLogger("TechnicalAnalysis");
  const [timeframe, setTimeframe] = useState("daily");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [orderBy] = useState("symbol");
  const [order] = useState("asc");
  const [activeFilters, setActiveFilters] = useState(0);
  const [expandedRow, setExpandedRow] = useState(null);
  const navigate = useNavigate();

  // --- FIX: Move these above useQuery ---
  const [indicatorFilter, setIndicatorFilter] = useState("");
  const [indicatorMin, setIndicatorMin] = useState("");
  const [indicatorMax, setIndicatorMax] = useState("");

  // Memoize the query function to prevent infinite loops
  const queryFn = useCallback(async () => {
    // Map frontend parameters to backend parameters
    const params = {
      page: page + 1,
      limit: rowsPerPage,
      symbol: symbolFilter || undefined,
      sortBy: orderBy,
      sortOrder: order,
    };

    // Map indicator filters to backend parameter names
    if (indicatorFilter) {
      switch (indicatorFilter) {
        case "rsi":
          if (indicatorMin) params.rsi_min = indicatorMin;
          if (indicatorMax) params.rsi_max = indicatorMax;
          break;
        case "macd":
          if (indicatorMin) params.macd_min = indicatorMin;
          if (indicatorMax) params.macd_max = indicatorMax;
          break;
        case "sma_20":
          if (indicatorMin) params.sma_min = indicatorMin;
          if (indicatorMax) params.sma_max = indicatorMax;
          break;
        default:
          // For other indicators, we'll need to add specific mappings
          break;
      }
    }

    const result = await getTechnicalData(timeframe, params);

    if (Array.isArray(result)) return { data: result };
    if (!Array.isArray(result?.data)) return { ...result, data: [] };
    return result;
  }, [
    timeframe,
    symbolFilter,
    indicatorFilter,
    indicatorMin,
    indicatorMax,
    page,
    rowsPerPage,
    orderBy,
    order,
  ]);

  // Fetch technical data
  const {
    data: technicalData,
    isLoading,
    error,
    _refetch,
  } = useQuery({
    queryKey: [
      "technicalAnalysis",
      timeframe,
      symbolFilter,
      indicatorFilter,
      indicatorMin,
      indicatorMax,
      page,
      rowsPerPage,
      orderBy,
      order,
    ],
    queryFn,
    onError: (error) =>
      logger.queryError("technicalAnalysis", error, {
        timeframe,
        symbolFilter,
        page,
      }),
    refetchInterval: 300000,
    retry: 2,
    staleTime: 60000,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  });

  // Update activeFilters count (consolidated from duplicate useEffects)
  useEffect(() => {
    let count = 0;
    if (symbolFilter) count++;
    if (indicatorFilter) count++;
    if (indicatorMin || indicatorMax) count++;
    setActiveFilters(count);
  }, [symbolFilter, indicatorFilter, indicatorMin, indicatorMax]);

  const handleSearch = () => {
    setSymbolFilter(searchInput.trim());
    setPage(0);
  };
  const handleClearSearch = () => {
    setSearchInput("");
    setSymbolFilter("");
    setPage(0);
  };
  const handleTimeframeChange = (e) => {
    setTimeframe(e.target.value);
    setPage(0);
  };

  const handlePageChange = (event, newPage) => {
    setPage(newPage);
  };
  const handleRowsPerPageChange = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Table columns (can be expanded)
  const columns = [
    { id: "symbol", label: "Symbol", sortable: true },
    { id: "date", label: "Date", sortable: true, format: formatDate },
    { id: "rsi", label: "RSI", sortable: true },
    { id: "macd", label: "MACD", sortable: true },
    { id: "macd_signal", label: "MACD Signal", sortable: true },
    { id: "macd_hist", label: "MACD Hist", sortable: true },
    { id: "adx", label: "ADX", sortable: true },
    { id: "atr", label: "ATR", sortable: true },
    { id: "mfi", label: "MFI", sortable: true },
    { id: "roc", label: "ROC", sortable: true },
    { id: "mom", label: "MOM", sortable: true },
    { id: "bbands_upper", label: "BB Upper", sortable: true },
    { id: "bbands_middle", label: "BB Middle", sortable: true },
    { id: "bbands_lower", label: "BB Lower", sortable: true },
    { id: "sma_10", label: "SMA 10", sortable: true },
    { id: "sma_20", label: "SMA 20", sortable: true },
    { id: "sma_50", label: "SMA 50", sortable: true },
    { id: "sma_150", label: "SMA 150", sortable: true },
    { id: "sma_200", label: "SMA 200", sortable: true },
    { id: "ema_4", label: "EMA 4", sortable: true },
    { id: "ema_9", label: "EMA 9", sortable: true },
    { id: "ema_21", label: "EMA 21", sortable: true },
    { id: "ad", label: "A/D", sortable: true },
    { id: "cmf", label: "CMF", sortable: true },
    { id: "td_sequential", label: "TD Seq", sortable: true },
    { id: "td_combo", label: "TD Combo", sortable: true },
    { id: "marketwatch", label: "MW", sortable: true },
    { id: "dm", label: "DM", sortable: true },
    { id: "pivot_high", label: "Pivot H", sortable: true },
    { id: "pivot_low", label: "Pivot L", sortable: true },
    { id: "pivot_high_triggered", label: "Pivot H Triggered", sortable: true },
    { id: "pivot_low_triggered", label: "Pivot L Triggered", sortable: true },
  ];

  // Helper to map icon string to MUI icon component
  const getIconComponent = (icon) => {
    switch (icon) {
      case "up":
        return <TrendingUp fontSize="small" color="inherit" />;
      case "down":
        return <TrendingDown fontSize="small" color="inherit" />;
      case "flat":
        return <HorizontalRule fontSize="small" color="inherit" />;
      case "neutral":
        return <ShowChart fontSize="small" color="inherit" />;
      case "info":
      default:
        return <InfoOutlined fontSize="small" color="inherit" />;
    }
  };

  // --- Accordion rendering for each row (fixed syntax, requirements met) ---
  const renderAccordionTable = () => (
    <Box sx={{ width: "100%" }}>
      {(Array.isArray(technicalData?.data) ? technicalData.data : []).map(
        (row, idx) => (
          <Accordion
            key={row.symbol + "-" + row.date + "-" + idx}
            expanded={expandedRow === idx}
            onChange={() => setExpandedRow(expandedRow === idx ? null : idx)}
            sx={{
              mb: 1,
              borderLeft: 4,
              borderColor:
                row.rsi > 70
                  ? "error.main"
                  : row.rsi < 30
                    ? "primary.main"
                    : "grey.300",
              boxShadow: expandedRow === idx ? 6 : 1,
            }}
          >
            <AccordionSummary
              expandIcon={<ExpandMore />}
              sx={{
                backgroundColor: expandedRow === idx ? "grey.100" : "grey.50",
                "&:hover": { backgroundColor: "grey.200" },
                minHeight: 100,
                "& .MuiAccordionSummary-content": {
                  margin: "16px 0",
                  flexDirection: "column",
                },
              }}
            >
              <Box sx={{ width: "100%" }}>
                {/* Top row - Symbol and key metrics */}
                <Grid container alignItems="center" spacing={2} sx={{ mb: 2 }}>
                  <Grid item xs={12} sm={3}>
                    <Box>
                      <Typography variant="h6" fontWeight="bold">
                        {row.symbol}
                      </Typography>
                      {row.company_name && (
                        <Typography
                          variant="body2"
                          color="text.secondary"
                          noWrap
                        >
                          {row.company_name}
                        </Typography>
                      )}
                      <Typography variant="caption" color="text.secondary">
                        {formatDate(row.date)}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={2}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        RSI
                      </Typography>
                      <Box display="flex" alignItems="center" gap={0.5}>
                        {getIconComponent(getTechStatus("rsi", row.rsi).icon)}
                        <Typography
                          variant="body2"
                          color={getTechStatus("rsi", row.rsi).color}
                          fontWeight="bold"
                        >
                          {formatNumber(row.rsi)}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={2}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        MACD
                      </Typography>
                      <Box display="flex" alignItems="center" gap={0.5}>
                        {getIconComponent(getTechStatus("macd", row.macd).icon)}
                        <Typography
                          variant="body2"
                          color={getTechStatus("macd", row.macd).color}
                          fontWeight="bold"
                        >
                          {formatNumber(row.macd)}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={2}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        ADX
                      </Typography>
                      <Box display="flex" alignItems="center" gap={0.5}>
                        {getIconComponent(getTechStatus("adx", row.adx).icon)}
                        <Typography
                          variant="body2"
                          color={getTechStatus("adx", row.adx).color}
                          fontWeight="bold"
                        >
                          {formatNumber(row.adx)}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={1.5}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        ATR
                      </Typography>
                      <Box display="flex" alignItems="center" gap={0.5}>
                        {getIconComponent(getTechStatus("atr", row.atr).icon)}
                        <Typography
                          variant="body2"
                          color={getTechStatus("atr", row.atr).color}
                          fontWeight="bold"
                        >
                          {formatNumber(row.atr)}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={1.5}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        MFI
                      </Typography>
                      <Box display="flex" alignItems="center" gap={0.5}>
                        {getIconComponent(getTechStatus("mfi", row.mfi).icon)}
                        <Typography
                          variant="body2"
                          color={getTechStatus("mfi", row.mfi).color}
                          fontWeight="bold"
                        >
                          {formatNumber(row.mfi)}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                </Grid>

                {/* Bottom row - Price info */}
                <Divider sx={{ mb: 1 }} />
                <Grid container spacing={1} alignItems="center">
                  <Grid item xs={6} sm={2}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        Price
                      </Typography>
                      <Typography variant="body2" fontWeight="bold">
                        $
                        {row.current_price
                          ? formatNumber(row.current_price, 2)
                          : "N/A"}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={2}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        Change
                      </Typography>
                      <Box display="flex" alignItems="center" gap={0.5}>
                        {row.price_direction &&
                          getIconComponent(row.price_direction)}
                        <Typography
                          variant="body2"
                          color={
                            row.price_direction === "up"
                              ? "success.main"
                              : row.price_direction === "down"
                                ? "error.main"
                                : "text.secondary"
                          }
                          fontWeight="bold"
                        >
                          {row.price_change_percent
                            ? `${row.price_change_percent > 0 ? "+" : ""}${formatNumber(row.price_change_percent, 2)}%`
                            : "N/A"}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={2.5}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        Range
                      </Typography>
                      <Typography
                        variant="body2"
                        fontWeight="bold"
                        sx={{
                          fontSize: "0.8rem",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          maxWidth: "100%",
                        }}
                      >
                        {row.high_price && row.low_price
                          ? `${formatNumber(row.low_price, 2)} - ${formatNumber(row.high_price, 2)}`
                          : "N/A"}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={1.5}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        Volume
                      </Typography>
                      <Typography
                        variant="body2"
                        fontWeight="bold"
                        sx={{
                          fontSize: "0.8rem",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                          maxWidth: "100%",
                        }}
                      >
                        {row.volume ? formatNumber(row.volume) : "N/A"}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} sm={1.5}>
                    <Box
                      display="flex"
                      flexDirection="column"
                      alignItems="flex-start"
                    >
                      <Typography variant="caption" color="text.secondary">
                        Open
                      </Typography>
                      <Typography variant="body2" fontWeight="bold">
                        $
                        {row.open_price
                          ? formatNumber(row.open_price, 2)
                          : "N/A"}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={1.5}>
                    <Button
                      variant="outlined"
                      size="small"
                      fullWidth
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/technical-history/${row.symbol}`);
                      }}
                      sx={{ mt: { xs: 1, sm: 0 } }}
                    >
                      History
                    </Button>
                  </Grid>
                </Grid>
              </Box>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                {columns
                  .filter((col) => col.id !== "symbol" && col.id !== "date")
                  .map((col) => (
                    <Grid item xs={12} sm={6} md={3} key={col.id}>
                      <Card variant="outlined" sx={{ height: "100%" }}>
                        <CardContent>
                          <Box display="flex" alignItems="center" gap={1}>
                            {getIconComponent(
                              getTechStatus(col.id, row[col.id]).icon
                            )}
                            <Typography variant="subtitle2">
                              {col.label}
                            </Typography>
                          </Box>
                          <Typography
                            variant="h6"
                            color={getTechStatus(col.id, row[col.id]).color}
                            fontWeight="bold"
                          >
                            {col.format
                              ? col.format(row[col.id])
                              : row[col.id] !== undefined &&
                                  row[col.id] !== null
                                ? formatNumber(row[col.id])
                                : "N/A"}
                          </Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
              </Grid>
            </AccordionDetails>
          </Accordion>
        )
      )}
    </Box>
  );

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 600 }}>
          Technical Analysis
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Technical indicators and market screening
        </Typography>
      </Box>

      {/* Technical Screener */}
      <Box display="flex" alignItems="flex-start" gap={4} sx={{ mt: 3 }}>
        {/* Left filter/search panel */}
        <Box minWidth={260} maxWidth={320}>
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Filter Technicals
              </Typography>
              <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                <InputLabel>Timeframe</InputLabel>
                <Select
                  value={timeframe}
                  label="Timeframe"
                  onChange={handleTimeframeChange}
                >
                  <MenuItem value="daily">Daily</MenuItem>
                  <MenuItem value="weekly">Weekly</MenuItem>
                  <MenuItem value="monthly">Monthly</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="Search Symbol"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
                onKeyPress={(e) => e.key === "Enter" && handleSearch()}
                size="small"
                fullWidth
                sx={{ mb: 2 }}
                placeholder="e.g., AAPL"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  ),
                }}
              />
              <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                <InputLabel>Indicator</InputLabel>
                <Select
                  value={indicatorFilter}
                  label="Indicator"
                  onChange={(e) => setIndicatorFilter(e.target.value)}
                >
                  <MenuItem value="">All</MenuItem>
                  <MenuItem value="rsi">RSI</MenuItem>
                  <MenuItem value="macd">MACD</MenuItem>
                  <MenuItem value="adx">ADX</MenuItem>
                  <MenuItem value="atr">ATR</MenuItem>
                  <MenuItem value="mfi">MFI</MenuItem>
                  <MenuItem value="roc">ROC</MenuItem>
                  <MenuItem value="mom">MOM</MenuItem>
                  <MenuItem value="bbands_upper">BB Upper</MenuItem>
                  <MenuItem value="bbands_middle">BB Middle</MenuItem>
                  <MenuItem value="bbands_lower">BB Lower</MenuItem>
                  <MenuItem value="sma_10">SMA 10</MenuItem>
                  <MenuItem value="sma_20">SMA 20</MenuItem>
                  <MenuItem value="sma_50">SMA 50</MenuItem>
                  <MenuItem value="sma_150">SMA 150</MenuItem>
                  <MenuItem value="sma_200">SMA 200</MenuItem>
                  <MenuItem value="ema_4">EMA 4</MenuItem>
                  <MenuItem value="ema_9">EMA 9</MenuItem>
                  <MenuItem value="ema_21">EMA 21</MenuItem>
                  <MenuItem value="ad">A/D</MenuItem>
                  <MenuItem value="cmf">CMF</MenuItem>
                  <MenuItem value="td_sequential">TD Seq</MenuItem>
                  <MenuItem value="td_combo">TD Combo</MenuItem>
                  <MenuItem value="marketwatch">MW</MenuItem>
                  <MenuItem value="dm">DM</MenuItem>
                  <MenuItem value="pivot_high">Pivot H</MenuItem>
                  <MenuItem value="pivot_low">Pivot L</MenuItem>
                  <MenuItem value="pivot_high_triggered">
                    Pivot H Triggered
                  </MenuItem>
                  <MenuItem value="pivot_low_triggered">
                    Pivot L Triggered
                  </MenuItem>
                </Select>
              </FormControl>
              <Box display="flex" gap={1} mb={2}>
                <TextField
                  label="Min Value"
                  type="number"
                  value={indicatorMin}
                  onChange={(e) => setIndicatorMin(e.target.value)}
                  size="small"
                  fullWidth
                  disabled={!indicatorFilter}
                />
                <TextField
                  label="Max Value"
                  type="number"
                  value={indicatorMax}
                  onChange={(e) => setIndicatorMax(e.target.value)}
                  size="small"
                  fullWidth
                  disabled={!indicatorFilter}
                />
              </Box>
              <Box display="flex" gap={1} mb={2}>
                <Button
                  variant="outlined"
                  onClick={handleSearch}
                  startIcon={<Search />}
                  disabled={isLoading}
                >
                  {symbolFilter ? "Search" : "Filter"}
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Clear />}
                  onClick={handleClearSearch}
                  disabled={isLoading || !symbolFilter}
                >
                  Clear
                </Button>
                <Chip
                  label={`${activeFilters} Filters`}
                  color={activeFilters > 0 ? "primary" : "default"}
                  icon={<FilterList />}
                />
              </Box>
            </CardContent>
          </Card>
        </Box>
        {/* Main content: overview + table */}
        <Box flex={1}>
          <Typography
            variant="h4"
            gutterBottom
            sx={{ mb: 2, mt: 1, textAlign: "left" }}
          >
            Technical Analysis
          </Typography>
          <Divider sx={{ mb: 2 }} />
          {/* Error/Loading/Empty states */}
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              Error loading technical data: {error.message}
            </Alert>
          )}
          {isLoading ? (
            <Box
              display="flex"
              flexDirection="column"
              alignItems="center"
              p={4}
            >
              <CircularProgress sx={{ mb: 2 }} />
              <Typography variant="body2" color="text.secondary">
                Loading technical data...
              </Typography>
            </Box>
          ) : (
            <>
              {(Array.isArray(technicalData?.data) ? technicalData.data : [])
                .length === 0 ? (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  No technical data found.
                </Alert>
              ) : (
                renderAccordionTable()
              )}
              {/* Pagination */}
              <TablePagination
                component="div"
                count={technicalData?.pagination?.total || 0}
                page={page}
                onPageChange={handlePageChange}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={handleRowsPerPageChange}
                rowsPerPageOptions={[10, 25, 50, 100]}
                sx={{ mt: 2 }}
              />
            </>
          )}
        </Box>
      </Box>
    </Container>
  );
}

export default TechnicalAnalysis;
