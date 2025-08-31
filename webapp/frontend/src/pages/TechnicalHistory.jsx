import { useState, useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getPriceHistory } from "../services/api";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Container,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  ArrowBack,
  Search,
  FilterList,
  GetApp,
  TableChart,
  ViewModule,
  ExpandMore,
  Clear,
} from "@mui/icons-material";
import { formatNumber, formatDate, formatCurrency } from "../utils/formatters";

// Main component
function PriceHistory() {
  const { symbol } = useParams();
  const navigate = useNavigate();

  // Core state
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [total, setTotal] = useState(0);

  // Pagination state
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // Filter state
  const [searchTerm, setSearchTerm] = useState("");
  const [timeframe, setTimeframe] = useState("daily");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [activeTab, setActiveTab] = useState(0);
  const [viewMode, setViewMode] = useState("table"); // 'table' or 'cards'
  const [showFilters, setShowFilters] = useState(false);

  // Technical filters
  const [_techFilters, _setTechFilters] = useState({
    rsi_min: "",
    rsi_max: "",
    macd_min: "",
    macd_max: "",
    sma_min: "",
    sma_max: "",
  });

  // Price filters
  const [priceFilters, setPriceFilters] = useState({
    price_min: "",
    price_max: "",
    volume_min: "",
    volume_max: "",
  });

  // Column visibility
  const [visibleColumns, setVisibleColumns] = useState({
    date: true,
    close: true,
    volume: true,
    rsi: true,
    macd: true,
    sma_20: true,
    sma_50: true,
    ema_12: true,
    bollinger_middle: false,
    stochastic_k: false,
    adx: false,
    atr: false,
  });

  // Define available columns with categories
  const columnCategories = {
    price: [
      { id: "date", label: "Date", format: formatDate },
      { id: "open", label: "Open", format: formatCurrency },
      { id: "high", label: "High", format: formatCurrency },
      { id: "low", label: "Low", format: formatCurrency },
      { id: "close", label: "Close", format: formatCurrency },
      { id: "volume", label: "Volume", format: (val) => formatNumber(val, 0) },
    ],
    momentum: [
      { id: "rsi", label: "RSI", format: (val) => formatNumber(val, 2) },
      { id: "macd", label: "MACD", format: (val) => formatNumber(val, 4) },
      {
        id: "macd_signal",
        label: "MACD Signal",
        format: (val) => formatNumber(val, 4),
      },
      {
        id: "stochastic_k",
        label: "Stoch %K",
        format: (val) => formatNumber(val, 2),
      },
      {
        id: "stochastic_d",
        label: "Stoch %D",
        format: (val) => formatNumber(val, 2),
      },
      {
        id: "williams_r",
        label: "Williams %R",
        format: (val) => formatNumber(val, 2),
      },
      { id: "cci", label: "CCI", format: (val) => formatNumber(val, 2) },
      {
        id: "momentum",
        label: "Momentum",
        format: (val) => formatNumber(val, 2),
      },
      { id: "roc", label: "ROC", format: (val) => formatNumber(val, 2) },
    ],
    trend: [
      { id: "sma_20", label: "SMA 20", format: formatCurrency },
      { id: "sma_50", label: "SMA 50", format: formatCurrency },
      { id: "ema_12", label: "EMA 12", format: formatCurrency },
      { id: "ema_26", label: "EMA 26", format: formatCurrency },
      { id: "adx", label: "ADX", format: (val) => formatNumber(val, 2) },
    ],
    volatility: [
      { id: "bollinger_upper", label: "BB Upper", format: formatCurrency },
      { id: "bollinger_middle", label: "BB Middle", format: formatCurrency },
      { id: "bollinger_lower", label: "BB Lower", format: formatCurrency },
      { id: "atr", label: "ATR", format: (val) => formatNumber(val, 4) },
    ],
    volume: [
      { id: "obv", label: "OBV", format: (val) => formatNumber(val, 0) },
      { id: "mfi", label: "MFI", format: (val) => formatNumber(val, 2) },
      { id: "ad", label: "A/D", format: (val) => formatNumber(val, 0) },
      { id: "cmf", label: "CMF", format: (val) => formatNumber(val, 4) },
    ],
  };

  // Get all available columns
  const allColumns = Object.values(columnCategories).flat();

  // Get visible columns for display
  const displayColumns = useMemo(() => {
    return allColumns.filter((col) => visibleColumns[col.id]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleColumns]);

  // Fetch data function
  const fetchData = async () => {
    if (!symbol) return;

    setLoading(true);
    setError(null);

    try {
      const params = {
        symbol: symbol.toUpperCase(),
        page: page + 1,
        limit: rowsPerPage,
        start_date: dateFrom || undefined,
        end_date: dateTo || undefined,
        ...Object.fromEntries(
          Object.entries(priceFilters).filter(([_, value]) => value !== "")
        ),
      };

      console.log("🔍 Fetching price history:", { timeframe, params });
      const result = await getPriceHistory(timeframe, params);

      if (result && result?.data) {
        setData(result?.data);
        setTotal(result.pagination?.total || 0);
      } else {
        setData([]);
        setTotal(0);
      }
    } catch (err) {
      console.error("❌ Error fetching price history:", err);
      setError(err.message || "Failed to load price history");
      setData([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  // Effects
  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, timeframe, page, rowsPerPage, dateFrom, dateTo, priceFilters]);

  // Filter data based on search term
  const filteredData = useMemo(() => {
    if (!searchTerm) return data;
    return data.filter((row) =>
      Object.values(row).some((value) =>
        String(value).toLowerCase().includes(searchTerm.toLowerCase())
      )
    );
  }, [data, searchTerm]);

  // Event handlers
  const handlePageChange = (event, newPage) => setPage(newPage);
  const handleRowsPerPageChange = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handleTimeframeChange = (event) => {
    setTimeframe(event.target.value);
    setPage(0);
  };

  const handlePriceFilterChange = (field, value) => {
    setPriceFilters((prev) => ({
      ...prev,
      [field]: value,
    }));
    setPage(0);
  };

  const clearFilters = () => {
    setDateFrom("");
    setDateTo("");
    setSearchTerm("");
    setPriceFilters({
      price_min: "",
      price_max: "",
      volume_min: "",
      volume_max: "",
    });
    setPage(0);
  };

  const toggleColumn = (columnId) => {
    setVisibleColumns((prev) => ({
      ...prev,
      [columnId]: !prev[columnId],
    }));
  };

  const exportData = () => {
    if (!(filteredData?.length || 0)) return;

    const headers = (displayColumns || []).map((col) => col.label).join(",");
    const rows = filteredData
      .map((row) =>
        displayColumns
          .map((col) => {
            const value = row[col.id];
            return col.format ? col.format(value) : value || "";
          })
          .join(",")
      )
      .join("\n");

    const csv = `${headers}\n${rows}`;
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${symbol}_${timeframe}_price_history.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Render summary stats
  const renderSummaryStats = () => {
    if (!(data?.length || 0)) return null;

    const latest = data[0];
    const dayChange = data.length > 1 ? latest.close - data[1].close : 0;
    const dayChangePercent =
      data.length > 1 ? (dayChange / data[1].close) * 100 : 0;

    const stats = [
      {
        label: "Latest Close",
        value: formatCurrency(latest.close),
        color: "primary",
      },
      {
        label: "Day Change",
        value: `${dayChange >= 0 ? "+" : ""}${formatCurrency(dayChange)}`,
        color: dayChange >= 0 ? "success" : "error",
      },
      {
        label: "Day Change %",
        value: `${dayChangePercent >= 0 ? "+" : ""}${dayChangePercent.toFixed(2)}%`,
        color: dayChangePercent >= 0 ? "success" : "error",
      },
      { label: "Volume", value: formatNumber(latest.volume, 0), color: "info" },
    ];

    return (
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Latest Data ({formatDate(latest.date)})
          </Typography>
          <Grid container spacing={2}>
            {(stats || []).map((stat, index) => (
              <Grid item xs={6} sm={3} key={index}>
                <Box textAlign="center">
                  <Typography variant="h6" color={`${stat.color}.main`}>
                    {stat.value}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {stat.label}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>
    );
  };

  // Render table view
  const renderTableView = () => (
    <Paper sx={{ width: "100%", overflow: "hidden" }}>
      <Box sx={{ overflowX: "auto" }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              {(displayColumns || []).map((column) => (
                <TableCell
                  key={column.id}
                  sx={{ fontWeight: "bold", minWidth: 100 }}
                >
                  {column.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {(filteredData || []).map((row, index) => (
              <TableRow hover key={`${row.date}-${index}`}>
                {(displayColumns || []).map((column) => {
                  const value = row[column.id];

                  return (
                    <TableCell
                      key={column.id}
                      align={typeof value === "number" ? "right" : "left"}
                    >
                      {column.format ? column.format(value) : value || "N/A"}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
      <TablePagination
        component="div"
        count={total}
        page={page}
        onPageChange={handlePageChange}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={handleRowsPerPageChange}
        rowsPerPageOptions={[10, 25, 50, 100]}
      />
    </Paper>
  );

  // Render card view
  const renderCardView = () => (
    <Box>
      <Grid container spacing={2}>
        {(filteredData || []).map((row, index) => (
          <Grid item xs={12} sm={6} md={4} key={`${row.date}-${index}`}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {formatDate(row.date)}
                </Typography>
                <Stack spacing={1}>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2">Close:</Typography>
                    <Typography variant="body2" fontWeight="bold">
                      {formatCurrency(row.close)}
                    </Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2">Volume:</Typography>
                    <Typography variant="body2">
                      {formatNumber(row.volume, 0)}
                    </Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2">Open:</Typography>
                    <Typography variant="body2">
                      {formatCurrency(row.open)}
                    </Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2">High:</Typography>
                    <Typography variant="body2" color="success.main">
                      {formatCurrency(row.high)}
                    </Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2">Low:</Typography>
                    <Typography variant="body2" color="error.main">
                      {formatCurrency(row.low)}
                    </Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      <Box display="flex" justifyContent="center" mt={3}>
        <TablePagination
          component="div"
          count={total}
          page={page}
          onPageChange={handlePageChange}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={handleRowsPerPageChange}
          rowsPerPageOptions={[6, 12, 24, 48]}
        />
      </Box>
    </Box>
  );

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* Header */}
      <Box
        display="flex"
        alignItems="center"
        justifyContent="space-between"
        mb={3}
      >
        <Box display="flex" alignItems="center" gap={2}>
          <IconButton onClick={() => navigate(-1)}>
            <ArrowBack />
          </IconButton>
          <Typography variant="h4">Price History - {symbol}</Typography>
        </Box>

        <Box display="flex" gap={1}>
          <Tooltip title="Export Data">
            <IconButton onClick={exportData} disabled={!(data?.length || 0)}>
              <GetApp />
            </IconButton>
          </Tooltip>
          <Tooltip title="Toggle View">
            <IconButton
              onClick={() =>
                setViewMode(viewMode === "table" ? "cards" : "table")
              }
            >
              {viewMode === "table" ? <ViewModule /> : <TableChart />}
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Controls */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={6} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Timeframe</InputLabel>
                <Select value={timeframe} onChange={handleTimeframeChange}>
                  <MenuItem value="daily">Daily</MenuItem>
                  <MenuItem value="weekly">Weekly</MenuItem>
                  <MenuItem value="monthly">Monthly</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <TextField
                fullWidth
                size="small"
                label="Search"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  ),
                  endAdornment: searchTerm && (
                    <InputAdornment position="end">
                      <IconButton
                        size="small"
                        onClick={() => setSearchTerm("")}
                      >
                        <Clear />
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>

            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="date"
                label="From Date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>

            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                type="date"
                label="To Date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>

            <Grid item xs={12} md={2}>
              <Box display="flex" gap={1}>
                <Button
                  variant="outlined"
                  startIcon={<FilterList />}
                  onClick={() => setShowFilters(!showFilters)}
                  size="small"
                >
                  Filters
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Clear />}
                  onClick={clearFilters}
                  size="small"
                >
                  Clear
                </Button>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Advanced Filters */}
      {showFilters && (
        <Accordion expanded={showFilters}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography>Advanced Filters & Column Selection</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={3}>
              {/* Price & Volume Filters */}
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>
                  Price & Volume Filters
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Min Price"
                      type="number"
                      step="0.01"
                      value={priceFilters.price_min}
                      onChange={(e) =>
                        handlePriceFilterChange("price_min", e.target.value)
                      }
                    />
                  </Grid>
                  <Grid item xs={6}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Max Price"
                      type="number"
                      step="0.01"
                      value={priceFilters.price_max}
                      onChange={(e) =>
                        handlePriceFilterChange("price_max", e.target.value)
                      }
                    />
                  </Grid>
                  <Grid item xs={6}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Min Volume"
                      type="number"
                      value={priceFilters.volume_min}
                      onChange={(e) =>
                        handlePriceFilterChange("volume_min", e.target.value)
                      }
                    />
                  </Grid>
                  <Grid item xs={6}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Max Volume"
                      type="number"
                      value={priceFilters.volume_max}
                      onChange={(e) =>
                        handlePriceFilterChange("volume_max", e.target.value)
                      }
                    />
                  </Grid>
                </Grid>
              </Grid>

              {/* Column Selection */}
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>
                  Visible Columns
                </Typography>
                <Tabs
                  value={activeTab}
                  onChange={handleTabChange}
                  variant="scrollable"
                >
                  {Object.keys(columnCategories).map((category, index) => (
                    <Tab
                      key={category}
                      value={index}
                      label={
                        category.charAt(0).toUpperCase() + category.slice(1)
                      }
                    />
                  ))}
                </Tabs>
                <Box sx={{ mt: 2, maxHeight: 200, overflow: "auto" }}>
                  {Object.entries(columnCategories).map(
                    ([category, columns], categoryIndex) =>
                      activeTab === categoryIndex && (
                        <Grid container spacing={1} key={category}>
                          {(columns || []).map((column) => (
                            <Grid item xs={6} key={column.id}>
                              <FormControlLabel
                                control={
                                  <Switch
                                    checked={visibleColumns[column.id] || false}
                                    onChange={() => toggleColumn(column.id)}
                                    size="small"
                                  />
                                }
                                label={column.label}
                              />
                            </Grid>
                          ))}
                        </Grid>
                      )
                  )}
                </Box>
              </Grid>
            </Grid>
          </AccordionDetails>
        </Accordion>
      )}

      {/* Summary Stats */}
      {renderSummaryStats()}

      {/* Main Content */}
      {loading ? (
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight={400}
        >
          <CircularProgress size={60} />
        </Box>
      ) : error ? (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
          <Button onClick={fetchData} sx={{ ml: 2 }}>
            Retry
          </Button>
        </Alert>
      ) : !(data?.length || 0) ? (
        <Alert severity="info">
          No technical data found for {symbol} in the {timeframe} timeframe.
        </Alert>
      ) : (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Showing {(filteredData?.length || 0)} of {total} records
          </Typography>
          {viewMode === "table" ? renderTableView() : renderCardView()}
        </>
      )}
    </Container>
  );
}

export default PriceHistory;
