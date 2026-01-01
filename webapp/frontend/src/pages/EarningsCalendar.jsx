import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { createComponentLogger } from "../utils/errorLogger";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Alert,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  TablePagination,
  TextField,
  InputAdornment,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  Button,
} from "@mui/material";
import {
  EventNote,
  TrendingUp,
  TrendingDown,
  Schedule,
  ShowChart,
  ExpandMore,
  Search,
  Clear,
} from "@mui/icons-material";
import { formatCurrency, formatPercentage } from "../utils/formatters";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const logger = createComponentLogger("EarningsCalendar");

function EarningsCalendar() {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [searchInput, setSearchInput] = useState("");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [expandedSymbol, setExpandedSymbol] = useState(null);

  const API_BASE = (import.meta.env && import.meta.env.VITE_API_URL) || "";

  // Fetch S&P 500 earnings trend data
  const {
    data: sp500TrendData,
    isLoading: sp500Loading,
    error: sp500Error,
  } = useQuery({
    queryKey: ["sp500EarningsTrend"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/earnings/sp500-trend?years=10`);
      if (!response.ok) throw new Error("Failed to fetch S&P 500 earnings trend");
      const json = await response.json();
      return json.data;
    },
    staleTime: 1000 * 60 * 60, // 1 hour
  });

  // Fetch weekly calendar events (upcoming earnings)
  const {
    data: weeklyCalendarData,
    isLoading: weeklyLoading,
    error: weeklyError,
  } = useQuery({
    queryKey: ["weeklyEarningsCalendar"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/earnings/calendar?period=upcoming&limit=50`);
      if (!response.ok) {
        const text = await response.text();
        logger.error("Weekly calendar fetch failed", {
          status: response.status,
          text,
        });
        throw new Error(
          `Failed to fetch weekly calendar: ${response.status} ${text}`
        );
      }
      const json = await response.json();
      // Backend returns new format: { items: [...calendar items], pagination: {...}, success: true }
      if (!json.items) throw new Error('No earnings calendar items returned');
      // Transform to component format for consistent handling
      return {
        data: json.items,
        success: json.success
      };
    },
    refetchInterval: 300000,
  });

  // Fetch all earnings data for symbol drill-down
  const {
    data: earningsData,
    isLoading: earningsLoading,
    error: earningsError,
  } = useQuery({
    queryKey: ["earningsAll", symbolFilter, page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        limit: rowsPerPage,
      });
      if (symbolFilter) params.append("symbol", symbolFilter);

      const response = await fetch(
        `${API_BASE}/api/earnings/info?${params}`
      );
      if (!response.ok) throw new Error("Failed to fetch earnings data");
      const json = await response.json();
      // Transform data response to match expected format for estimates
      if (!json.data?.estimates) throw new Error('No earnings estimates available');
      return {
        data: json.data.estimates,
        success: json.success
      };
    },
    refetchInterval: 300000,
  });

  // Quality score removed from data model

  // Fetch detailed data for expanded symbol
  const {
    data: symbolDetails,
    isLoading: detailsLoading,
  } = useQuery({
    queryKey: ["earningsDetails", expandedSymbol],
    queryFn: async () => {
      // Validate that expandedSymbol is a valid stock symbol (not metadata keys)
      if (!expandedSymbol || expandedSymbol === "data" || expandedSymbol === "pagination") return null;

      logger.info(`Fetching earnings details for ${expandedSymbol}`);
      const dataRes = await fetch(`${API_BASE}/api/earnings/info?symbol=${encodeURIComponent(expandedSymbol)}`).then((r) => {
        if (!r.ok) throw new Error(`Failed to fetch earnings info: ${r.status}`);
        return r.json();
      });

      logger.info(`Received data for ${expandedSymbol}:`, {
        hasEstimates: !!dataRes.data?.estimates,
        hasHistory: !!dataRes.data?.history,
        hasSuprises: !!dataRes.data?.surprises,
        estimateCount: dataRes.data?.estimates?.length || 0,
        historyCount: dataRes.data?.history?.length || 0,
        surpriseCount: dataRes.data?.surprises?.length || 0
      });

      // Debug: Log actual surprise data
      if (dataRes.data?.surprises?.length > 0) {
        console.log(`✅ SURPRISES FOUND for ${expandedSymbol}:`, dataRes.data.surprises);
      } else {
        console.log(`⚠️ NO SURPRISES for ${expandedSymbol}`, {
          hasData: !!dataRes.data,
          surprisesArray: dataRes.data?.surprises,
          allDataKeys: dataRes.data ? Object.keys(dataRes.data) : 'no data'
        });
      }

      // Transform estimates to flat structure for accordion display
      const estimates = dataRes.data?.estimates || [];

      const transformedEstimates = estimates.map(e => ({
        period: e.period,
        avg_estimate: e.eps?.average_estimate,
        low_estimate: e.eps?.low_estimate,
        high_estimate: e.eps?.high_estimate,
        number_of_analysts: e.number_of_analysts,
        growth_percent: e.eps?.growth_percent
      }));

      const history = dataRes.data?.history || [];
      const surprises = dataRes.data?.surprises || [];

      logger.info(`Transformed data for ${expandedSymbol}:`, {
        transformedEstimatesCount: transformedEstimates.length,
        historyCount: history.length,
        surprisesCount: surprises.length
      });

      return {
        history,
        epsRevisions: { data: transformedEstimates },
        surprises
      };
    },
    enabled: !!expandedSymbol && expandedSymbol !== "data" && expandedSymbol !== "pagination",
    staleTime: 0,
    gcTime: 0,
  });

  const handleSearch = () => {
    setSymbolFilter(searchInput.toUpperCase());
    setPage(0);
  };

  const handleClearSearch = () => {
    setSearchInput("");
    setSymbolFilter("");
    setPage(0);
  };

  const handleToggleExpand = (symbol) => {
    setExpandedSymbol(expandedSymbol === symbol ? null : symbol);
  };

  const getSurpriseColor = (surprise) => {
    if (surprise > 5) return "success.main";
    if (surprise > 0) return "success.light";
    if (surprise < -5) return "error.main";
    if (surprise < 0) return "error.light";
    return "grey.500";
  };

  const getSurpriseIcon = (surprise) => {
    if (surprise > 0) return <TrendingUp sx={{ fontSize: 16 }} />;
    if (surprise < 0) return <TrendingDown sx={{ fontSize: 16 }} />;
    return <ShowChart sx={{ fontSize: 16 }} />;
  };

  // Group earnings by date - show all upcoming earnings grouped by date
  const weeklyEvents = useMemo(() => {
    const dateMap = new Map(); // Track formatted date -> { date object, events array }

    // Populate events into the dates
    // API response: { data: [...], success: true }
    let events = weeklyCalendarData?.data || [];
    if (!Array.isArray(events)) {
      events = [];
    }

    if (Array.isArray(events)) {
      events.forEach(event => {
        try {
          // Parse date string directly (YYYY-MM-DD format)
          const dateStr = event.date.split('T')[0]; // Get just the date part
          const [year, month, day] = dateStr.split('-');
          const parsedYear = parseInt(year, 10);
          const parsedMonth = parseInt(month, 10);
          const parsedDay = parseInt(day, 10);

          // Validate parsed values are valid numbers
          if (isNaN(parsedYear) || isNaN(parsedMonth) || isNaN(parsedDay)) {
            throw new Error('Invalid date components');
          }

          const eventDate = new Date(parsedYear, parsedMonth - 1, parsedDay);

          const formattedDate = eventDate.toLocaleDateString("en-US", {
            weekday: "short",
            month: "short",
            day: "numeric",
          });

          if (!dateMap.has(formattedDate)) {
            dateMap.set(formattedDate, { dateObject: eventDate, events: [] });
          }
          dateMap.get(formattedDate).events.push(event);
        } catch (e) {
          console.error("Error parsing event date:", event.date, e);
        }
      });
    }

    // Sort dates chronologically
    const sortedEntries = Array.from(dateMap.entries())
      .sort((a, b) => a[1].dateObject.getTime() - b[1].dateObject.getTime());

    // Convert to object preserving insertion order
    const eventsByDate = Object.fromEntries(
      sortedEntries.map(([formattedDate, { events: eventsArray }]) => [formattedDate, eventsArray])
    );

    return eventsByDate;
  }, [weeklyCalendarData]);

  // Format earnings data for table
  // API response: { data: [...], success: true }
  const estimatesArray = earningsData?.data || [];

  // Filter to show only current year estimates (0y) to avoid duplicates
  const primaryEstimates = estimatesArray.filter(e => e.period === "0y");

  const sortedEstimates = primaryEstimates.sort((a, b) => {
    // Sort by symbol alphabetically
    return a.symbol.localeCompare(b.symbol);
  });

  // Client-side pagination
  const earningsRows = sortedEstimates.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  if (weeklyLoading && !weeklyCalendarData) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="400px"
        >
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Earnings Calendar
      </Typography>

      {/* Summary Stats */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <EventNote color="primary" sx={{ mr: 1 }} />
                <Typography variant="h6">Total Earnings</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color="primary">
                {(weeklyCalendarData?.data || []).length}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Historical records loaded
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <ShowChart color="success" sx={{ mr: 1 }} />
                <Typography variant="h6">Recent</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color="success.main">
                {Object.values(weeklyEvents).reduce(
                  (sum, events) => sum + events.length,
                  0
                )}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Reported (last 60 days)
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <TrendingUp color="success" sx={{ mr: 1 }} />
                <Typography variant="h6">Total Companies</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color="text.primary">
                {earningsRows.length}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                With estimates
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="body2" color="text.secondary">
                Overall score
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* S&P 500 Earnings Trend */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <ShowChart color="primary" />
            <Typography variant="h6">S&P 500 Earnings Trend</Typography>
          </Box>

          {sp500Error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              Failed to load S&P 500 earnings data. Please try again later.
            </Alert>
          )}

          {sp500Loading ? (
            <Box display="flex" justifyContent="center" py={3}>
              <CircularProgress />
            </Box>
          ) : sp500TrendData ? (
            <Grid container spacing={3}>
              <Grid item xs={12} md={4}>
                <Box>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Latest Earnings (Quarterly)
                  </Typography>
                  <Typography variant="h4" fontWeight="bold" color="primary">
                    ${sp500TrendData.summary?.latestEarnings?.toFixed(2) || 'N/A'}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {sp500TrendData.summary?.latestDate
                      ? new Date(sp500TrendData.summary.latestDate).toLocaleDateString()
                      : 'N/A'}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} md={4}>
                <Box>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Year-over-Year Change
                  </Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    {sp500TrendData.summary?.changePercent > 0 ? (
                      <TrendingUp color="success" fontSize="large" />
                    ) : (
                      <TrendingDown color="error" fontSize="large" />
                    )}
                    <Typography
                      variant="h4"
                      fontWeight="bold"
                      color={sp500TrendData.summary?.changePercent > 0 ? 'success.main' : 'error.main'}
                    >
                      {sp500TrendData.summary?.changePercent || '0'}%
                    </Typography>
                  </Box>
                </Box>
              </Grid>
              <Grid item xs={12} md={4}>
                <Box>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Trend
                  </Typography>
                  <Chip
                    label={sp500TrendData.summary?.trend?.toUpperCase() || 'NEUTRAL'}
                    color={
                      sp500TrendData.summary?.trend === 'increasing'
                        ? 'success'
                        : sp500TrendData.summary?.trend === 'decreasing'
                        ? 'error'
                        : 'default'
                    }
                    sx={{ mt: 1, fontSize: '1.1rem', px: 2, py: 3 }}
                  />
                  <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                    Based on 10-year historical data from FRED
                  </Typography>
                </Box>
              </Grid>

              {/* Earnings Trend Chart */}
              <Grid item xs={12}>
                {sp500TrendData.earnings && sp500TrendData.earnings.length > 0 ? (
                  <Box sx={{ width: '100%', height: 400, mt: 3 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={sp500TrendData.earnings.map(point => ({
                          date: new Date(point.date).toLocaleDateString('en-US', {
                            year: 'numeric',
                            month: 'short'
                          }),
                          earnings: point.value,
                          fullDate: point.date
                        }))}
                        margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis
                          dataKey="date"
                          angle={-45}
                          textAnchor="end"
                          height={80}
                          tick={{ fontSize: 12 }}
                        />
                        <YAxis
                          label={{ value: 'Earnings Per Share ($)', angle: -90, position: 'insideLeft' }}
                          tick={{ fontSize: 12 }}
                        />
                        <Tooltip
                          formatter={(value) => [`$${value?.toFixed(2)}`, 'EPS']}
                          labelFormatter={(label) => `Date: ${label}`}
                        />
                        <Legend />
                        <Line
                          type="monotone"
                          dataKey="earnings"
                          stroke="#1976d2"
                          strokeWidth={2}
                          dot={{ r: 4 }}
                          activeDot={{ r: 6 }}
                          name="S&P 500 Earnings"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </Box>
                ) : (
                  <Alert severity="warning" sx={{ mt: 3 }}>
                    <Typography variant="body2">
                      📊 <strong>No S&P 500 earnings data available yet.</strong>
                    </Typography>
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      To populate this chart:
                    </Typography>
                    <Typography variant="body2" component="div" sx={{ mt: 1, pl: 2 }}>
                      1. Get free FRED API key: <a href="https://fredaccount.stlouisfed.org/apikeys" target="_blank" rel="noopener noreferrer">https://fredaccount.stlouisfed.org/apikeys</a><br />
                      2. Add to .env.local: FRED_API_KEY=your_key<br />
                      3. Run: python3 loadecondata.py
                    </Typography>
                  </Alert>
                )}
              </Grid>

              <Grid item xs={12}>
                <Alert severity="info" sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    📊 <strong>Data Source:</strong> S&P 500 quarterly earnings per share from Federal Reserve Economic Data (FRED).
                    This shows the aggregate earnings trend for the entire S&P 500 index over the past 10 years.
                    {sp500TrendData.earnings?.length > 0 && (
                      <> Showing {sp500TrendData.earnings.length} quarterly data points.</>
                    )}
                  </Typography>
                </Alert>
              </Grid>
            </Grid>
          ) : (
            <Typography color="text.secondary">No S&P 500 earnings data available.</Typography>
          )}
        </CardContent>
      </Card>

      {/* Weekly Earnings Calendar */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={3}>
            <Schedule color="primary" />
            <Typography variant="h6">Recently Reported Earnings</Typography>
          </Box>

          {weeklyError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              Failed to load weekly calendar. Please try again later.
            </Alert>
          )}

          {weeklyLoading ? (
            <Box display="flex" justifyContent="center" py={3}>
              <CircularProgress size={28} />
            </Box>
          ) : (
            <Grid container spacing={2}>
              {Object.entries(weeklyEvents).map(([date, events]) => (
                <Grid item xs={12} sm={6} md={2.4} key={date}>
                  <Card variant="outlined" sx={{ height: "100%" }}>
                    <CardContent>
                      <Typography
                        variant="subtitle2"
                        color="primary"
                        gutterBottom
                      >
                        {date}
                      </Typography>
                      <Divider sx={{ mb: 1 }} />
                      <Box sx={{ maxHeight: 200, overflowY: "auto" }}>
                        {events.length > 0 ? (
                          events.map((event, idx) => (
                            <Box
                              key={`${event.symbol}-${idx}`}
                              sx={{ mb: 1, cursor: "pointer" }}
                              onClick={() => {
                                setSearchInput(event.symbol);
                                setSymbolFilter(event.symbol);
                                setExpandedSymbol(event.symbol);
                                setPage(0);
                              }}
                            >
                              <Typography
                                variant="body2"
                                fontWeight="bold"
                                color="primary"
                              >
                                {event.symbol}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {event.title}
                              </Typography>
                            </Box>
                          ))
                        ) : (
                          <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 2 }}>
                            None
                          </Typography>
                        )}
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}
        </CardContent>
      </Card>

      {/* Search */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" gap={2} alignItems="center">
            <TextField
              placeholder="Search symbol (e.g., AAPL)"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
              onKeyPress={(e) => {
                if (e.key === "Enter") handleSearch();
              }}
              size="small"
              sx={{ flex: 1, maxWidth: 400 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search />
                  </InputAdornment>
                ),
              }}
            />
            <Button
              variant="contained"
              onClick={handleSearch}
              disabled={!searchInput}
            >
              Search
            </Button>
            {symbolFilter && (
              <Button
                variant="outlined"
                onClick={handleClearSearch}
                startIcon={<Clear />}
              >
                Clear
              </Button>
            )}
          </Box>
        </CardContent>
      </Card>

      {/* Error Handling */}
      {earningsError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load earnings data. Please try again later.
        </Alert>
      )}

      {/* Earnings Table */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Earnings Estimates & Details
          </Typography>

          {earningsLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <CircularProgress />
            </Box>
          ) : earningsRows.length === 0 ? (
            <Typography variant="body2" color="text.secondary" align="center" py={4}>
              No earnings data found. Try a different search.
            </Typography>
          ) : (
            <TableContainer component={Paper} elevation={0}>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: "grey.50" }}>
                    <TableCell width={50}></TableCell>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Company</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {earningsRows.map((row, index) => (
                    <React.Fragment key={`${row.symbol}-${index}`}>
                      <TableRow
                        hover
                        onClick={() => handleToggleExpand(row.symbol)}
                        sx={{ cursor: "pointer" }}
                      >
                        <TableCell>
                          <ExpandMore
                            sx={{
                              transform:
                                expandedSymbol === row.symbol
                                  ? "rotate(180deg)"
                                  : "rotate(0deg)",
                              transition: "transform 0.2s",
                            }}
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {row.symbol}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            {row.company_name}
                          </Typography>
                        </TableCell>
                      </TableRow>

                      {/* Expanded Details */}
                      {expandedSymbol === row.symbol && (
                        <TableRow>
                          <TableCell colSpan={4} sx={{ p: 0 }}>
                            <Box sx={{ p: 3, backgroundColor: "grey.50" }}>
                              {detailsLoading ? (
                                <Box display="flex" justifyContent="center" py={3}>
                                  <CircularProgress size={28} />
                                </Box>
                              ) : symbolDetails ? (
                                <Box>
                                  {/* Earnings Estimates Accordion */}
                                  <Accordion defaultExpanded>
                                    <AccordionSummary expandIcon={<ExpandMore />}>
                                      <Typography variant="subtitle1" fontWeight="bold">
                                        📊 Earnings Estimates
                                      </Typography>
                                    </AccordionSummary>
                                    <AccordionDetails>
                                      <Box width="100%">
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow sx={{ backgroundColor: "grey.100" }}>
                                                <TableCell>Period</TableCell>
                                                <TableCell align="right">Avg Est</TableCell>
                                                <TableCell align="right">Range</TableCell>
                                                <TableCell align="right">Analysts</TableCell>
                                                <TableCell align="right">Growth</TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {(symbolDetails?.epsRevisions?.data?.slice(0, 4)?.length ?? 0) > 0 ? (
                                                symbolDetails?.epsRevisions?.data?.slice(0, 4)?.map((e, idx) => (
                                                  <TableRow key={`eps-rev-${e.period}-${idx}`}>
                                                    <TableCell>
                                                      <Chip label={e.period} size="small" variant="outlined" />
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Typography variant="body2" fontWeight="bold">
                                                        {formatCurrency(e.avg_estimate)}
                                                      </Typography>
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Typography variant="caption" color="text.secondary">
                                                        {formatCurrency(e.low_estimate)} - {formatCurrency(e.high_estimate)}
                                                      </Typography>
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Chip label={e.number_of_analysts} size="small" variant="outlined" />
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      {e.growth_percent != null ? (
                                                        <Box display="flex" alignItems="center" justifyContent="flex-end" gap={0.5}>
                                                          {getSurpriseIcon(e.growth_percent)}
                                                          <Typography variant="body2" sx={{ color: getSurpriseColor(e.growth_percent) }}>
                                                            {formatPercentage(e.growth_percent / 100)}
                                                          </Typography>
                                                        </Box>
                                                      ) : (
                                                        <Typography variant="body2" color="text.secondary">N/A</Typography>
                                                      )}
                                                    </TableCell>
                                                  </TableRow>
                                                ))
                                              ) : (
                                                <TableRow>
                                                  <TableCell colSpan={5} align="center" sx={{ py: 2 }}>
                                                    No estimates data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </Box>
                                    </AccordionDetails>
                                  </Accordion>

                                  {/* Earnings History Accordion */}
                                  <Accordion defaultExpanded>
                                    <AccordionSummary expandIcon={<ExpandMore />}>
                                      <Typography variant="subtitle1" fontWeight="bold">
                                        📈 Earnings History
                                      </Typography>
                                    </AccordionSummary>
                                    <AccordionDetails>
                                      <Box width="100%">
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow sx={{ backgroundColor: "grey.100" }}>
                                                <TableCell>Quarter</TableCell>
                                                <TableCell align="right">Actual</TableCell>
                                                <TableCell align="right">Estimate</TableCell>
                                                <TableCell align="right">Surprise %</TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {(symbolDetails?.history?.slice(0, 4)?.length ?? 0) > 0 ? (
                                                symbolDetails?.history?.slice(0, 4)?.map((h, idx) => (
                                                  <TableRow key={`hist-${h.quarter}-${idx}`}>
                                                    <TableCell>{new Date(h.quarter).toLocaleDateString()}</TableCell>
                                                    <TableCell align="right">{formatCurrency(h.eps_actual)}</TableCell>
                                                    <TableCell align="right">{formatCurrency(h.eps_estimate)}</TableCell>
                                                    <TableCell align="right">
                                                      <Chip
                                                        label={formatPercentage(h.surprise_percent * 100)}
                                                        size="small"
                                                        color={h.surprise_percent > 0 ? "success" : h.surprise_percent < 0 ? "error" : "default"}
                                                      />
                                                    </TableCell>
                                                  </TableRow>
                                                ))
                                              ) : (
                                                <TableRow>
                                                  <TableCell colSpan={4} align="center" sx={{ py: 2 }}>
                                                    No history data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </Box>
                                    </AccordionDetails>
                                  </Accordion>

                                  {/* EPS Revisions Accordion */}
                                  <Accordion defaultExpanded>
                                    <AccordionSummary expandIcon={<ExpandMore />}>
                                      <Typography variant="subtitle1" fontWeight="bold">
                                        🎯 EPS Revisions
                                      </Typography>
                                    </AccordionSummary>
                                    <AccordionDetails>
                                      <Box width="100%">
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow sx={{ backgroundColor: "grey.100" }}>
                                                <TableCell>Period</TableCell>
                                                <TableCell align="right">Avg Est</TableCell>
                                                <TableCell align="right">Low</TableCell>
                                                <TableCell align="right">High</TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {(symbolDetails?.epsRevisions?.data?.slice(0, 4)?.length ?? 0) > 0 ? (
                                                symbolDetails?.epsRevisions?.data?.slice(0, 4)?.map((r, idx) => (
                                                  <TableRow key={`rev-${r.period}-${idx}`}>
                                                    <TableCell>{r.period}</TableCell>
                                                    <TableCell align="right">{formatCurrency(r.avg_estimate)}</TableCell>
                                                    <TableCell align="right">{formatCurrency(r.low_estimate)}</TableCell>
                                                    <TableCell align="right">{formatCurrency(r.high_estimate)}</TableCell>
                                                  </TableRow>
                                                ))
                                              ) : (
                                                <TableRow>
                                                  <TableCell colSpan={4} align="center" sx={{ py: 2 }}>
                                                    No revisions data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </Box>
                                    </AccordionDetails>
                                  </Accordion>

                                  {/* Earnings Surprises Accordion */}
                                  <Accordion defaultExpanded>
                                    <AccordionSummary expandIcon={<ExpandMore />}>
                                      <Typography variant="subtitle1" fontWeight="bold">
                                        ⭐ Earnings Surprises
                                      </Typography>
                                    </AccordionSummary>
                                    <AccordionDetails>
                                      <Box width="100%">
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow sx={{ backgroundColor: "grey.100" }}>
                                                <TableCell>Quarter</TableCell>
                                                <TableCell align="right">Actual</TableCell>
                                                <TableCell align="right">Estimate</TableCell>
                                                <TableCell align="right">Surprise %</TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {(symbolDetails?.surprises?.slice(0, 4)?.length ?? 0) > 0 ? (
                                                symbolDetails?.surprises?.slice(0, 4)?.map((s, idx) => (
                                                  <TableRow key={`surp-${s.date}-${idx}`}>
                                                    <TableCell>{new Date(s.date).toLocaleDateString()}</TableCell>
                                                    <TableCell align="right">{formatCurrency(s.earnings?.actual)}</TableCell>
                                                    <TableCell align="right">{formatCurrency(s.earnings?.estimate)}</TableCell>
                                                    <TableCell align="right">
                                                      <Chip
                                                        label={s.earnings?.surprise_percent != null ? formatPercentage(s.earnings.surprise_percent / 100) : "-"}
                                                        size="small"
                                                        color={s.earnings?.surprise_percent > 0 ? "success" : s.earnings?.surprise_percent < 0 ? "error" : "default"}
                                                      />
                                                    </TableCell>
                                                  </TableRow>
                                                ))
                                              ) : (
                                                <TableRow>
                                                  <TableCell colSpan={4} align="center" sx={{ py: 2 }}>
                                                    No surprises data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </Box>
                                    </AccordionDetails>
                                  </Accordion>
                                </Box>
                              ) : (
                                <Typography color="text.secondary">
                                  No detailed data available
                                </Typography>
                              )}
                            </Box>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          <TablePagination
            component="div"
            count={sortedEstimates.length}
            page={page}
            onPageChange={(_e, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </CardContent>
      </Card>
    </Container>
  );
}

export default EarningsCalendar;
