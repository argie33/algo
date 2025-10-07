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
  Analytics,
  Schedule,
  ShowChart,
  ExpandMore,
  Search,
  Clear,
} from "@mui/icons-material";
import { formatCurrency, formatPercentage } from "../utils/formatters";

const logger = createComponentLogger("EarningsCalendar");

function EarningsCalendar() {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [searchInput, setSearchInput] = useState("");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [expandedSymbol, setExpandedSymbol] = useState(null);

  const API_BASE = (import.meta.env && import.meta.env.VITE_API_URL) || "";

  // Fetch weekly calendar events
  const {
    data: weeklyCalendarData,
    isLoading: weeklyLoading,
    error: weeklyError,
  } = useQuery({
    queryKey: ["weeklyEarningsCalendar"],
    queryFn: async () => {
      const params = new URLSearchParams({
        type: "this_week",
        event_type: "earnings",
      });
      const response = await fetch(`${API_BASE}/api/calendar/events?${params}`);
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
      return response.json();
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
        page: page + 1,
        limit: rowsPerPage,
      });
      if (symbolFilter) params.append("symbol", symbolFilter);

      const response = await fetch(
        `${API_BASE}/api/calendar/earnings-estimates?${params}`
      );
      if (!response.ok) throw new Error("Failed to fetch earnings data");
      return response.json();
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
      if (!expandedSymbol) return null;

      const [history, epsRevisions, epsTrend, metrics] = await Promise.all([
        fetch(
          `${API_BASE}/api/calendar/earnings-history?symbol=${expandedSymbol}`
        ).then((r) => (r.ok ? r.json() : { data: {} })),
        fetch(
          `${API_BASE}/api/analysts/${encodeURIComponent(
            expandedSymbol
          )}/eps-revisions`
        ).then((r) => (r.ok ? r.json() : { data: [] })),
        fetch(
          `${API_BASE}/api/analysts/${encodeURIComponent(
            expandedSymbol
          )}/eps-trend`
        ).then((r) => (r.ok ? r.json() : { data: [] })),
        fetch(
          `${API_BASE}/api/calendar/earnings-metrics?symbol=${expandedSymbol}`
        ).then((r) => (r.ok ? r.json() : { data: {} })),
      ]);

      return { history, epsRevisions, epsTrend, metrics };
    },
    enabled: !!expandedSymbol,
    staleTime: 60000,
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

  // Group weekly calendar by day - always show all weekdays
  const weeklyEvents = useMemo(() => {
    // Get current week's Monday-Friday dates
    const today = new Date();
    const currentDay = today.getDay(); // 0 = Sunday, 1 = Monday, etc.
    const mondayOffset = currentDay === 0 ? -6 : 1 - currentDay; // If Sunday, go back 6 days, else calculate offset to Monday

    const weekDates = {};
    for (let i = 0; i < 5; i++) { // Mon-Fri only
      const date = new Date(today);
      date.setDate(today.getDate() + mondayOffset + i);
      const dateKey = date.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
      weekDates[dateKey] = [];
    }

    // Populate events into the dates
    const events = weeklyCalendarData?.data?.data ?? weeklyCalendarData?.data ?? [];
    events.forEach(event => {
      const date = new Date(event.start_date).toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
      if (weekDates[date]) {
        weekDates[date].push(event);
      }
    });

    return weekDates;
  }, [weeklyCalendarData]);

  // Format earnings data for table - one row per symbol
  const earningsRows = Object.entries(earningsData?.data || {})
    .map(([symbol, group]) => ({
      symbol,
      company_name: group.company_name,
      estimates: group.estimates || [],
    }))
    .sort((a, b) => {
      // Sort by symbol alphabetically
      return a.symbol.localeCompare(b.symbol);
    });

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
                <Typography variant="h6">Upcoming Events</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color="primary">
                {weeklyCalendarData?.summary?.upcoming_events || 0}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Next 30 days
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={1}>
                <ShowChart color="success" sx={{ mr: 1 }} />
                <Typography variant="h6">This Week</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color="success.main">
                {Object.values(weeklyEvents).reduce(
                  (sum, events) => sum + events.length,
                  0
                )}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Companies reporting
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

      {/* Weekly Earnings Calendar */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={3}>
            <Schedule color="primary" />
            <Typography variant="h6">This Week&apos;s Earnings</Typography>
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
                        <TableCell align="center">
                          {row.quality_score !== null ? (
                            <Chip
                              label={row.quality_score.toFixed(1)}
                              size="small"
                              color={
                                row.quality_score >= 70
                                  ? "success"
                                  : row.quality_score >= 50
                                    ? "warning"
                                    : "error"
                              }
                            />
                          ) : (
                            <Typography variant="caption" color="text.secondary">
                              N/A
                            </Typography>
                          )}
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
                                <Grid container spacing={3}>
                                  {/* Earnings Estimates */}
                                  <Grid item xs={12} md={6}>
                                    <Accordion defaultExpanded>
                                      <AccordionSummary expandIcon={<ExpandMore />}>
                                        <Typography variant="subtitle1" fontWeight="bold">
                                          Earnings Estimates
                                        </Typography>
                                      </AccordionSummary>
                                      <AccordionDetails>
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow>
                                                <TableCell>Period</TableCell>
                                                <TableCell align="right">Avg Est</TableCell>
                                                <TableCell align="right">Range</TableCell>
                                                <TableCell align="right">Analysts</TableCell>
                                                <TableCell align="right">Growth</TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {row.estimates?.length > 0 ? (
                                                row.estimates.map((est, idx) => (
                                                  <TableRow key={idx}>
                                                    <TableCell>
                                                      <Chip
                                                        label={est.period}
                                                        size="small"
                                                        variant="outlined"
                                                      />
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Typography variant="body2" fontWeight="bold">
                                                        {formatCurrency(est.avg_estimate)}
                                                      </Typography>
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Typography variant="caption" color="text.secondary">
                                                        {formatCurrency(est.low_estimate)} - {formatCurrency(est.high_estimate)}
                                                      </Typography>
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Chip
                                                        label={est.number_of_analysts}
                                                        size="small"
                                                        variant="outlined"
                                                      />
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Box display="flex" alignItems="center" justifyContent="flex-end" gap={0.5}>
                                                        {getSurpriseIcon(est.growth)}
                                                        <Typography
                                                          variant="body2"
                                                          sx={{ color: getSurpriseColor(est.growth) }}
                                                        >
                                                          {formatPercentage(est.growth / 100)}
                                                        </Typography>
                                                      </Box>
                                                    </TableCell>
                                                  </TableRow>
                                                ))
                                              ) : (
                                                <TableRow>
                                                  <TableCell colSpan={5} align="center">
                                                    No estimates data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </AccordionDetails>
                                    </Accordion>
                                  </Grid>

                                  {/* Earnings History */}
                                  <Grid item xs={12} md={6}>
                                    <Accordion defaultExpanded>
                                      <AccordionSummary expandIcon={<ExpandMore />}>
                                        <Typography variant="subtitle1" fontWeight="bold">
                                          Earnings History
                                        </Typography>
                                      </AccordionSummary>
                                      <AccordionDetails>
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow>
                                                <TableCell>Quarter</TableCell>
                                                <TableCell align="right">
                                                  Actual
                                                </TableCell>
                                                <TableCell align="right">
                                                  Estimate
                                                </TableCell>
                                                <TableCell align="right">
                                                  Surprise %
                                                </TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {symbolDetails.history?.data?.[
                                                expandedSymbol
                                              ]?.history
                                                ?.slice(0, 4)
                                                .map((h, idx) => (
                                                  <TableRow key={idx}>
                                                    <TableCell>
                                                      {new Date(
                                                        h.quarter
                                                      ).toLocaleDateString()}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      {formatCurrency(h.eps_actual)}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      {formatCurrency(h.eps_estimate)}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Chip
                                                        label={formatPercentage(
                                                          h.surprise_percent / 100
                                                        )}
                                                        size="small"
                                                        color={
                                                          h.surprise_percent > 0
                                                            ? "success"
                                                            : h.surprise_percent < 0
                                                              ? "error"
                                                              : "default"
                                                        }
                                                      />
                                                    </TableCell>
                                                  </TableRow>
                                                )) || (
                                                <TableRow>
                                                  <TableCell
                                                    colSpan={4}
                                                    align="center"
                                                  >
                                                    No history data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </AccordionDetails>
                                    </Accordion>
                                  </Grid>

                                  {/* EPS Revisions */}
                                  <Grid item xs={12} md={6}>
                                    <Accordion defaultExpanded>
                                      <AccordionSummary expandIcon={<ExpandMore />}>
                                        <Typography variant="subtitle1" fontWeight="bold">
                                          EPS Revisions
                                        </Typography>
                                      </AccordionSummary>
                                      <AccordionDetails>
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow>
                                                <TableCell>Period</TableCell>
                                                <TableCell align="right">
                                                  Avg Est
                                                </TableCell>
                                                <TableCell align="right">
                                                  Low
                                                </TableCell>
                                                <TableCell align="right">
                                                  High
                                                </TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {symbolDetails.epsRevisions?.data
                                                ?.slice(0, 4)
                                                .map((r, idx) => (
                                                  <TableRow key={idx}>
                                                    <TableCell>{r.period}</TableCell>
                                                    <TableCell align="right">
                                                      {formatCurrency(r.avg_estimate)}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      {formatCurrency(r.low_estimate)}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      {formatCurrency(r.high_estimate)}
                                                    </TableCell>
                                                  </TableRow>
                                                )) || (
                                                <TableRow>
                                                  <TableCell
                                                    colSpan={4}
                                                    align="center"
                                                  >
                                                    No revisions data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </AccordionDetails>
                                    </Accordion>
                                  </Grid>

                                  {/* EPS Trend */}
                                  <Grid item xs={12} md={6}>
                                    <Accordion defaultExpanded>
                                      <AccordionSummary expandIcon={<ExpandMore />}>
                                        <Typography variant="subtitle1" fontWeight="bold">
                                          EPS Trend
                                        </Typography>
                                      </AccordionSummary>
                                      <AccordionDetails>
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow>
                                                <TableCell>Period</TableCell>
                                                <TableCell align="right">
                                                  Current Est
                                                </TableCell>
                                                <TableCell align="right">
                                                  Year Ago
                                                </TableCell>
                                                <TableCell align="right">
                                                  Growth
                                                </TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {symbolDetails.epsTrend?.data
                                                ?.slice(0, 4)
                                                .map((t, idx) => (
                                                  <TableRow key={idx}>
                                                    <TableCell>{t.period}</TableCell>
                                                    <TableCell align="right">
                                                      {formatCurrency(t.avg_estimate)}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      {formatCurrency(t.year_ago_eps)}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      <Chip
                                                        label={formatPercentage(
                                                          t.growth / 100
                                                        )}
                                                        size="small"
                                                        color={
                                                          t.growth > 0
                                                            ? "success"
                                                            : t.growth < 0
                                                              ? "error"
                                                              : "default"
                                                        }
                                                      />
                                                    </TableCell>
                                                  </TableRow>
                                                )) || (
                                                <TableRow>
                                                  <TableCell
                                                    colSpan={4}
                                                    align="center"
                                                  >
                                                    No trend data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </AccordionDetails>
                                    </Accordion>
                                  </Grid>

                                  {/* Earnings Metrics */}
                                  <Grid item xs={12} md={6}>
                                    <Accordion defaultExpanded>
                                      <AccordionSummary expandIcon={<ExpandMore />}>
                                        <Typography variant="subtitle1" fontWeight="bold">
                                          Earnings Quality Metrics
                                        </Typography>
                                      </AccordionSummary>
                                      <AccordionDetails>
                                        <TableContainer>
                                          <Table size="small">
                                            <TableHead>
                                              <TableRow>
                                                <TableCell>Date</TableCell>
                                                <TableCell align="right">
                                                  EPS YoY
                                                </TableCell>
                                                <TableCell align="right">
                                                  Rev YoY
                                                </TableCell>
                                              </TableRow>
                                            </TableHead>
                                            <TableBody>
                                              {symbolDetails.metrics?.data?.[
                                                expandedSymbol
                                              ]?.metrics
                                                ?.slice(0, 4)
                                                .map((m, idx) => (
                                                  <TableRow key={idx}>
                                                    <TableCell>
                                                      {m.report_date}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      {m.eps_yoy_growth
                                                        ? `${m.eps_yoy_growth.toFixed(1)}%`
                                                        : "N/A"}
                                                    </TableCell>
                                                    <TableCell align="right">
                                                      {m.revenue_yoy_growth
                                                        ? `${m.revenue_yoy_growth.toFixed(1)}%`
                                                        : "N/A"}
                                                    </TableCell>
                                                  </TableRow>
                                                )) || (
                                                <TableRow>
                                                  <TableCell
                                                    colSpan={4}
                                                    align="center"
                                                  >
                                                    No metrics data
                                                  </TableCell>
                                                </TableRow>
                                              )}
                                            </TableBody>
                                          </Table>
                                        </TableContainer>
                                      </AccordionDetails>
                                    </Accordion>
                                  </Grid>
                                </Grid>
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
            count={earningsData?.pagination?.total || earningsRows.length}
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
