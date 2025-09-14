import { useState } from "react";
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
  Tabs,
  Tab,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TablePagination,
  Avatar,
  LinearProgress,
  TextField,
  Button,
} from "@mui/material";
import {
  EventNote,
  TrendingUp,
  TrendingDown,
  HorizontalRule,
  Analytics,
  Schedule,
  AttachMoney,
  ShowChart,
} from "@mui/icons-material";
import { formatCurrency, formatPercentage } from "../utils/formatters";

// Create component-specific logger
const logger = createComponentLogger("EarningsCalendar");

function EarningsCalendar() {
  const [activeTab, setActiveTab] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [timeFilter, setTimeFilter] = useState("upcoming");

  // EPS Revisions state
  const [epsSymbol, setEpsSymbol] = useState("AAPL");
  const [epsInput, setEpsInput] = useState("AAPL");

  const API_BASE = (import.meta.env && import.meta.env.VITE_API_URL) || "";

  // Fetch calendar events
  const {
    data: calendarData,
    isLoading: calendarLoading,
    error: calendarError,
  } = useQuery({
    queryKey: ["calendarEvents", timeFilter, page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        type: timeFilter,
        page: page + 1,
        limit: rowsPerPage,
      });
      const response = await fetch(`${API_BASE}/api/calendar/events?${params}`);
      if (!response.ok) {
        const text = await response.text();
        logger.error("Calendar events fetch failed", {
          status: response.status,
          text,
        });
        throw new Error(
          `Failed to fetch calendar data: ${response.status} ${text}`
        );
      }
      return response.json();
    },
    enabled: activeTab === 0,
    refetchInterval: 300000, // Refresh every 5 minutes
  });

  // Fetch earnings estimates
  const { data: estimatesData, isLoading: estimatesLoading } = useQuery({
    queryKey: ["earningsEstimates", page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page + 1,
        limit: rowsPerPage,
      });
      const response = await fetch(
        `${API_BASE}/api/calendar/earnings-estimates?${params}`
      );
      if (!response.ok) throw new Error("Failed to fetch estimates data");
      return response.json();
    },
    enabled: activeTab === 1,
    refetchInterval: 300000,
  });

  // Fetch earnings history
  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ["earningsHistory", page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page + 1,
        limit: rowsPerPage,
      });
      const response = await fetch(
        `${API_BASE}/api/calendar/earnings-history?${params}`
      );
      if (!response.ok) throw new Error("Failed to fetch history data");
      return response.json();
    },
    enabled: activeTab === 2,
    refetchInterval: 600000, // Refresh every 10 minutes
  });

  // EPS Revisions fetch
  const {
    data: epsRevisionsData,
    isLoading: epsRevisionsLoading,
    error: epsRevisionsError,
    refetch: refetchEps,
  } = useQuery({
    queryKey: ["epsRevisions", epsSymbol],
    queryFn: async () => {
      const url = `${API_BASE}/api/analysts/${encodeURIComponent(epsSymbol)}/eps-revisions`;
      const response = await fetch(url);
      if (!response.ok) throw new Error("Failed to fetch EPS revisions");
      return response.json();
    },
    enabled: activeTab === 3 && !!epsSymbol,
    staleTime: 60000,
  });

  // EPS Trend fetch
  const {
    data: epsTrendData,
    isLoading: epsTrendLoading,
    error: epsTrendError,
    refetch: refetchEpsTrend,
  } = useQuery({
    queryKey: ["epsTrend", epsSymbol],
    queryFn: async () => {
      const url = `${API_BASE}/api/analysts/${encodeURIComponent(epsSymbol)}/eps-trend`;
      const response = await fetch(url);
      if (!response.ok) throw new Error("Failed to fetch EPS trend");
      return response.json();
    },
    enabled: activeTab === 4 && !!epsSymbol,
    staleTime: 60000,
  });

  // Earnings Metrics fetch
  const {
    data: earningsMetricsData,
    isLoading: earningsMetricsLoading,
    error: earningsMetricsError,
    refetch: refetchEarningsMetrics,
  } = useQuery({
    queryKey: ["earningsMetrics", epsSymbol, page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page + 1,
        limit: rowsPerPage,
      });
      const url = `${API_BASE}/api/calendar/earnings-metrics?${params}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error("Failed to fetch earnings metrics");
      return response.json();
    },
    enabled: activeTab === 5 && !!epsSymbol,
    staleTime: 60000,
  });

  const getEventTypeChip = (eventType) => {
    const typeConfig = {
      earnings: { color: "#3B82F6", icon: <ShowChart />, label: "Earnings" },
      dividend: { color: "#10B981", icon: <AttachMoney />, label: "Dividend" },
      split: { color: "#8B5CF6", icon: <Analytics />, label: "Stock Split" },
      meeting: { color: "#F59E0B", icon: <EventNote />, label: "Meeting" },
    };

    const config =
      typeConfig[eventType?.toLowerCase()] || typeConfig["earnings"];

    return (
      <Chip
        label={config.label}
        size="small"
        icon={config.icon}
        sx={{
          backgroundColor: config.color,
          color: "white",
          fontWeight: "medium",
          "& .MuiChip-icon": {
            color: "white",
          },
        }}
      />
    );
  };

  const getSurpriseColor = (surprise) => {
    if (surprise > 5) return "success.main";
    if (surprise > 0) return "success.light";
    if (surprise < -5) return "error.main";
    if (surprise < 0) return "error.light";
    return "grey.500";
  };

  const getSurpriseIcon = (surprise) => {
    if (surprise > 0) return <TrendingUp />;
    if (surprise < 0) return <TrendingDown />;
    return <TrendingUp />;
  };

  const CalendarEventsTable = () => (
    <TableContainer component={Paper} elevation={0}>
      <Table>
        <TableHead>
          <TableRow sx={{ backgroundColor: "grey.50" }}>
            <TableCell>Symbol</TableCell>
            <TableCell>Event Type</TableCell>
            <TableCell>Date</TableCell>
            <TableCell>Title</TableCell>
            <TableCell>Time to Event</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {calendarData?.data?.data?.map((event, index) => (
            <TableRow key={`${event.symbol}-${index}`} hover>
              <TableCell>
                <Typography variant="body2" fontWeight="bold">
                  {event.symbol}
                </Typography>
              </TableCell>
              <TableCell>{getEventTypeChip(event.event_type)}</TableCell>
              <TableCell>
                <Typography variant="body2">
                  {new Date(event.start_date).toLocaleDateString()}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2" noWrap>
                  {event.title}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2" color="text.secondary">
                  {Math.ceil(
                    (new Date(event.start_date) - new Date()) /
                      (1000 * 60 * 60 * 24)
                  )}{" "}
                  days
                </Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const EarningsEstimatesTable = () => (
    <TableContainer component={Paper} elevation={0}>
      <Table>
        <TableHead>
          <TableRow sx={{ backgroundColor: "grey.50" }}>
            <TableCell>Symbol</TableCell>
            <TableCell>Company</TableCell>
            <TableCell>Period</TableCell>
            <TableCell align="right">Avg Estimate</TableCell>
            <TableCell align="right">Low</TableCell>
            <TableCell align="right">High</TableCell>
            <TableCell align="right">Analysts</TableCell>
            <TableCell align="right">Growth</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {Object.entries(estimatesData?.data || {}).map(([symbol, group]) =>
            (group.estimates || []).map((estimate, index) => (
              <TableRow key={`${symbol}-${estimate.period}-${index}`} hover>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    {symbol}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{group.company_name}</Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={estimate.period}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" fontWeight="bold">
                    {formatCurrency(estimate.avg_estimate)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  {formatCurrency(estimate.low_estimate)}
                </TableCell>
                <TableCell align="right">
                  {formatCurrency(estimate.high_estimate)}
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {estimate.number_of_analysts}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="flex-end"
                    gap={1}
                  >
                    <Avatar
                      sx={{
                        bgcolor: getSurpriseColor(estimate.growth),
                        width: 24,
                        height: 24,
                      }}
                    >
                      {getSurpriseIcon(estimate.growth)}
                    </Avatar>
                    <Typography
                      variant="body2"
                      sx={{ color: getSurpriseColor(estimate.growth) }}
                    >
                      {formatPercentage(estimate.growth / 100)}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const EarningsHistoryTable = () => (
    <TableContainer component={Paper} elevation={0}>
      <Table>
        <TableHead>
          <TableRow sx={{ backgroundColor: "grey.50" }}>
            <TableCell>Symbol</TableCell>
            <TableCell>Company</TableCell>
            <TableCell>Quarter</TableCell>
            <TableCell align="right">Actual EPS</TableCell>
            <TableCell align="right">Estimated EPS</TableCell>
            <TableCell align="right">Difference</TableCell>
            <TableCell align="right">Surprise %</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {Object.entries(historyData?.data || {}).map(([symbol, group]) =>
            (group.history || []).map((history, index) => (
              <TableRow key={`${symbol}-${history.quarter}-${index}`} hover>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    {symbol}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">{group.company_name}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {new Date(history.quarter).toLocaleDateString()}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" fontWeight="bold">
                    {formatCurrency(history.eps_actual)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  {formatCurrency(history.eps_estimate)}
                </TableCell>
                <TableCell align="right">
                  <Typography
                    variant="body2"
                    sx={{
                      color:
                        history.eps_difference >= 0
                          ? "success.main"
                          : "error.main",
                    }}
                  >
                    {formatCurrency(history.eps_difference)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="flex-end"
                    gap={1}
                  >
                    <Avatar
                      sx={{
                        bgcolor: getSurpriseColor(history.surprise_percent),
                        width: 24,
                        height: 24,
                      }}
                    >
                      {getSurpriseIcon(history.surprise_percent)}
                    </Avatar>
                    <Typography
                      variant="body2"
                      sx={{ color: getSurpriseColor(history.surprise_percent) }}
                    >
                      {formatPercentage(history.surprise_percent / 100)}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const SummaryCard = ({ title, value, subtitle, icon, color }) => (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" mb={1}>
          {icon}
          <Typography variant="h6" ml={1}>
            {title}
          </Typography>
        </Box>
        <Typography variant="h4" sx={{ color, fontWeight: "bold" }}>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
      </CardContent>
    </Card>
  );

  const isLoading =
    calendarLoading ||
    (activeTab === 1 && estimatesLoading) ||
    (activeTab === 2 && historyLoading) ||
    (activeTab === 3 && epsRevisionsLoading) ||
    (activeTab === 4 && epsTrendLoading) ||
    (activeTab === 5 && earningsMetricsLoading);

  if (isLoading && !calendarData && !estimatesData && !historyData) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
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
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Earnings Calendar & Estimates
      </Typography>

      {/* Summary Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Upcoming Events"
            value={calendarData?.summary?.upcoming_events || 0}
            subtitle="Next 30 days"
            icon={<Schedule />}
            color="#3B82F6"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Earnings This Week"
            value={calendarData?.summary?.this_week || 0}
            subtitle="Companies reporting"
            icon={<ShowChart />}
            color="#10B981"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Positive Surprises"
            value={historyData?.summary?.positive_surprises || 0}
            subtitle="Last quarter"
            icon={<TrendingUp />}
            color="#059669"
          />
        </Grid>
        <Grid item xs={12} md={3}>
          <SummaryCard
            title="Estimates Updated"
            value={estimatesData?.summary?.recent_updates || 0}
            subtitle="Last 7 days"
            icon={<Analytics />}
            color="#8B5CF6"
          />
        </Grid>
      </Grid>

      {/* Error Handling */}
      {calendarError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load calendar data. Please try again later.
        </Alert>
      )}

      {/* Tabs */}
      <Box mb={3}>
        <Tabs
          value={activeTab}
          onChange={(e, newValue) => setActiveTab(newValue)}
        >
          <Tab value={0} label="Calendar Events" icon={<Schedule />} />
          <Tab value={1} label="Earnings Estimates" icon={<ShowChart />} />
          <Tab value={2} label="Earnings History" icon={<Analytics />} />
          <Tab value={3} label="EPS Revisions" icon={<TrendingUp />} />
          <Tab value={4} label="EPS Trend" icon={<TrendingDown />} />
          <Tab value={5} label="Earnings Metrics" icon={<HorizontalRule />} />
        </Tabs>
      </Box>

      {/* Filters for Calendar Tab */}
      {activeTab === 0 && (
        <Grid container spacing={2} mb={3}>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth>
              <InputLabel>Time Filter</InputLabel>
              <Select
                value={timeFilter}
                label="Time Filter"
                onChange={(e) => setTimeFilter(e.target.value)}
              >
                <MenuItem value="upcoming">Upcoming Events</MenuItem>
                <MenuItem value="this_week">This Week</MenuItem>
                <MenuItem value="next_week">Next Week</MenuItem>
                <MenuItem value="this_month">This Month</MenuItem>
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      )}

      {/* Loading indicator */}
      {isLoading && <LinearProgress sx={{ mb: 2 }} />}

      {/* Content */}
      <Card>
        <CardContent>
          {activeTab === 0 && (
            <>
              <Typography variant="h6" gutterBottom>
                Earnings Calendar - {timeFilter.replace("_", " ").toUpperCase()}
              </Typography>
              <CalendarEventsTable />
            </>
          )}

          {activeTab === 1 && (
            <>
              <Typography variant="h6" gutterBottom>
                Earnings Estimates
              </Typography>
              <EarningsEstimatesTable />
            </>
          )}

          {activeTab === 2 && (
            <>
              <Typography variant="h6" gutterBottom>
                Earnings History & Surprises
              </Typography>
              <EarningsHistoryTable />
            </>
          )}

          {activeTab === 3 && (
            <>
              <Typography variant="h6" gutterBottom>
                EPS Revisions Lookup
              </Typography>
              <Box display="flex" alignItems="center" gap={2} mb={2}>
                <TextField
                  label="Symbol"
                  value={epsInput}
                  onChange={(e) => setEpsInput(e.target.value.toUpperCase())}
                  size="small"
                  sx={{ width: 120 }}
                  inputProps={{ maxLength: 8 }}
                />
                <Button
                  variant="contained"
                  onClick={() => {
                    setEpsSymbol(epsInput);
                    refetchEps();
                  }}
                  disabled={epsRevisionsLoading || !epsInput}
                >
                  Lookup
                </Button>
              </Box>
              {epsRevisionsLoading ? (
                <Box display="flex" justifyContent="center" my={3}>
                  <CircularProgress size={28} />
                </Box>
              ) : epsRevisionsError ? (
                <Alert severity="error">
                  Failed to load EPS revisions: {epsRevisionsError.message}
                </Alert>
              ) : epsRevisionsData?.data?.length ? (
                <TableContainer component={Paper} sx={{ mt: 2 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Period</TableCell>
                        <TableCell align="right">Up Last 7d</TableCell>
                        <TableCell align="right">Up Last 30d</TableCell>
                        <TableCell align="right">Down Last 7d</TableCell>
                        <TableCell align="right">Down Last 30d</TableCell>
                        <TableCell align="right">Fetched At</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(epsRevisionsData.data || []).map((row, idx) => (
                        <TableRow key={row.period + idx}>
                          <TableCell>{row.period}</TableCell>
                          <TableCell align="right">
                            {row.up_last7days ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.up_last30days ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.down_last7days ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.down_last30days ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.fetched_at
                              ? new Date(row.fetched_at).toLocaleString()
                              : "-"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Typography variant="body2" color="text.secondary" mt={2}>
                  No EPS revisions data found for <b>{epsSymbol}</b>.
                </Typography>
              )}
            </>
          )}
          {activeTab === 4 && (
            <>
              <Typography variant="h6" gutterBottom>
                EPS Trend Lookup
              </Typography>
              <Box display="flex" alignItems="center" gap={2} mb={2}>
                <TextField
                  label="Symbol"
                  value={epsInput}
                  onChange={(e) => setEpsInput(e.target.value.toUpperCase())}
                  size="small"
                  sx={{ width: 120 }}
                  inputProps={{ maxLength: 8 }}
                />
                <Button
                  variant="contained"
                  onClick={() => {
                    setEpsSymbol(epsInput);
                    refetchEpsTrend();
                  }}
                  disabled={epsTrendLoading || !epsInput}
                >
                  Lookup
                </Button>
              </Box>
              {epsTrendLoading ? (
                <Box display="flex" justifyContent="center" my={3}>
                  <CircularProgress size={28} />
                </Box>
              ) : epsTrendError ? (
                <Alert severity="error">
                  Failed to load EPS trend: {epsTrendError.message}
                </Alert>
              ) : epsTrendData?.data?.length ? (
                <TableContainer component={Paper} sx={{ mt: 2 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Period</TableCell>
                        <TableCell align="right">Current</TableCell>
                        <TableCell align="right">7 Days Ago</TableCell>
                        <TableCell align="right">30 Days Ago</TableCell>
                        <TableCell align="right">60 Days Ago</TableCell>
                        <TableCell align="right">90 Days Ago</TableCell>
                        <TableCell align="right">Fetched At</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(epsTrendData.data || []).map((row, idx) => (
                        <TableRow key={row.period + idx}>
                          <TableCell>{row.period}</TableCell>
                          <TableCell align="right">
                            {row.current ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.days7ago ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.days30ago ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.days60ago ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.days90ago ?? "-"}
                          </TableCell>
                          <TableCell align="right">
                            {row.fetched_at
                              ? new Date(row.fetched_at).toLocaleString()
                              : "-"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Typography variant="body2" color="text.secondary" mt={2}>
                  No EPS trend data found for <b>{epsSymbol}</b>.
                </Typography>
              )}
            </>
          )}
          {activeTab === 5 && (
            <>
              <Typography variant="h6" gutterBottom>
                Earnings Metrics Lookup
              </Typography>
              <Box display="flex" alignItems="center" gap={2} mb={2}>
                <TextField
                  label="Symbol"
                  value={epsInput}
                  onChange={(e) => setEpsInput(e.target.value.toUpperCase())}
                  size="small"
                  sx={{ width: 120 }}
                  inputProps={{ maxLength: 8 }}
                />
                <Button
                  variant="contained"
                  onClick={() => {
                    setEpsSymbol(epsInput);
                    refetchEarningsMetrics();
                  }}
                  disabled={earningsMetricsLoading || !epsInput}
                >
                  Lookup
                </Button>
              </Box>
              {earningsMetricsLoading ? (
                <Box display="flex" justifyContent="center" my={3}>
                  <CircularProgress size={28} />
                </Box>
              ) : earningsMetricsError ? (
                <Alert severity="error">
                  Failed to load earnings metrics:{" "}
                  {earningsMetricsError.message}
                </Alert>
              ) : (
                <TableContainer component={Paper} sx={{ mt: 2 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Report Date</TableCell>
                        <TableCell align="right">EPS Growth 1Q</TableCell>
                        <TableCell align="right">EPS Growth 2Q</TableCell>
                        <TableCell align="right">EPS Growth 4Q</TableCell>
                        <TableCell align="right">EPS Growth 8Q</TableCell>
                        <TableCell align="right">EPS Accel Qtrs</TableCell>
                        <TableCell align="right">Surprise Last Q</TableCell>
                        <TableCell align="right">Est Rev 1M</TableCell>
                        <TableCell align="right">Est Rev 3M</TableCell>
                        <TableCell align="right">Est Rev 6M</TableCell>
                        <TableCell align="right">Annual EPS 1Y</TableCell>
                        <TableCell align="right">Annual EPS 3Y</TableCell>
                        <TableCell align="right">Annual EPS 5Y</TableCell>
                        <TableCell align="right">Consec EPS Yrs</TableCell>
                        <TableCell align="right">Est Change This Yr</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {Array.isArray(
                        earningsMetricsData?.data?.[epsSymbol]?.metrics
                      ) &&
                      earningsMetricsData?.data[epsSymbol].metrics.length > 0 ? (
                        (earningsMetricsData?.data[epsSymbol]?.metrics || []).map(
                          (row, idx) => (
                            <TableRow key={row.report_date + idx}>
                              <TableCell>{row.report_date}</TableCell>
                              <TableCell align="right">
                                {row.eps_growth_1q ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_growth_2q ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_growth_4q ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_growth_8q ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_acceleration_qtrs ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_surprise_last_q ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_estimate_revision_1m ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_estimate_revision_3m ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_estimate_revision_6m ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.annual_eps_growth_1y ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.annual_eps_growth_3y ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.annual_eps_growth_5y ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.consecutive_eps_growth_years ?? "-"}
                              </TableCell>
                              <TableCell align="right">
                                {row.eps_estimated_change_this_year ?? "-"}
                              </TableCell>
                            </TableRow>
                          )
                        )
                      ) : (
                        <TableRow>
                          <TableCell colSpan={15} align="center">
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              mt={2}
                            >
                              No earnings metrics data found for{" "}
                              <b>{epsSymbol}</b>.
                            </Typography>
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </>
          )}

          <TablePagination
            component="div"
            count={
              activeTab === 0
                ? calendarData?.pagination?.total || 0
                : activeTab === 1
                  ? estimatesData?.pagination?.total || 0
                  : activeTab === 2
                    ? historyData?.pagination?.total || 0
                    : activeTab === 3
                      ? epsRevisionsData?.pagination?.total || 0
                      : activeTab === 4
                        ? epsTrendData?.pagination?.total || 0
                        : earningsMetricsData?.pagination?.total || 0
            }
            page={page}
            onPageChange={(e, newPage) => setPage(newPage)}
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
