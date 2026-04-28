import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Container,
  Box,
  Typography,
  Alert,
  Card,
  CardContent,
  Grid,
  Tab,
  Tabs,
  CircularProgress,
  TextField,
  Autocomplete,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Divider,
} from "@mui/material";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { getStocks, getBalanceSheet, getIncomeStatement, getCashFlowStatement, getKeyMetrics } from "../services/api";
import { formatCurrency, formatNumber } from "../utils/formatters";

// ─── constants ──────────────────────────────────────────────────────────────

const EXCLUDED_KEYS = new Set([
  "id", "symbol", "fiscal_year", "fiscal_quarter",
  "created_at", "updated_at", "fetched_at",
]);

const CHART_COLORS = ["#1976d2", "#e91e63", "#4caf50", "#ff9800", "#9c27b0", "#00bcd4"];

// Key metrics to chart for each statement type (in display order)
const INCOME_CHART_KEYS = [
  { key: "total_revenue",       label: "Revenue" },
  { key: "gross_profit",        label: "Gross Profit" },
  { key: "operating_income",    label: "Operating Income" },
  { key: "net_income",          label: "Net Income" },
];

const BALANCE_CHART_KEYS = [
  { key: "total_assets",              label: "Total Assets" },
  { key: "total_liabilities_net_minority_interest", label: "Total Liabilities" },
  { key: "stockholders_equity",       label: "Stockholders Equity" },
  { key: "total_debt",                label: "Total Debt" },
];

const CASHFLOW_CHART_KEYS = [
  { key: "operating_cash_flow",       label: "Operating CF" },
  { key: "investing_cash_flow",       label: "Investing CF" },
  { key: "financing_cash_flow",       label: "Financing CF" },
  { key: "free_cash_flow",            label: "Free Cash Flow" },
];

// ─── helpers ────────────────────────────────────────────────────────────────

const formatColHeader = (key) =>
  key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

const formatCellVal = (value) => {
  if (value === null || value === undefined || value === "") return "—";
  const num = parseFloat(value);
  if (isNaN(num)) return String(value);
  if (Math.abs(num) >= 1000) return formatCurrency(num);
  return num.toFixed(2);
};

const toMillions = (value) => {
  const num = parseFloat(value);
  if (isNaN(num)) return null;
  return +(num / 1e6).toFixed(2);
};

const tooltipFormatter = (value) => {
  if (value === null || value === undefined) return "N/A";
  return `$${formatNumber(value * 1e6)}`;
};

// ─── sub-components ─────────────────────────────────────────────────────────

/**
 * Renders a scrollable financial table.
 * Rows = time periods (fiscal years / quarters), columns = all numeric fields.
 */
function FinancialTable({ rows }) {
  if (!rows || rows.length === 0) {
    return <Alert severity="info">No data available for selected period.</Alert>;
  }

  const allKeys = Object.keys(rows[0]).filter((k) => !EXCLUDED_KEYS.has(k));

  return (
    <Box sx={{ overflowX: "auto" }}>
      <TableContainer component={Paper} sx={{ maxHeight: 520 }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              <TableCell
                sx={{
                  fontWeight: "bold",
                  minWidth: 110,
                  position: "sticky",
                  left: 0,
                  zIndex: 3,
                  backgroundColor: "#f5f5f5",
                }}
              >
                Period
              </TableCell>
              {allKeys.map((key) => (
                <TableCell
                  key={key}
                  align="right"
                  sx={{ fontWeight: "bold", whiteSpace: "nowrap", minWidth: 150, backgroundColor: "#f5f5f5" }}
                >
                  {formatColHeader(key)}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row, idx) => (
              <TableRow
                key={idx}
                sx={{ "&:hover": { backgroundColor: "#f0f7ff" } }}
              >
                <TableCell
                  sx={{
                    fontWeight: 600,
                    position: "sticky",
                    left: 0,
                    backgroundColor: idx % 2 === 0 ? "#ffffff" : "#fafafa",
                    zIndex: 1,
                  }}
                >
                  {row.fiscal_year}
                  {row.fiscal_quarter ? ` Q${row.fiscal_quarter}` : ""}
                </TableCell>
                {allKeys.map((key) => (
                  <TableCell
                    key={key}
                    align="right"
                    sx={{ whiteSpace: "nowrap" }}
                  >
                    {formatCellVal(row[key])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

/**
 * Builds chart data from financial rows and a list of key/label pairs.
 * Data is sorted ascending by fiscal_year so charts read left-to-right.
 * Values are converted to millions for readability.
 */
function buildChartData(rows, chartKeys) {
  if (!rows || rows.length === 0) return [];

  // Sort ascending for the chart
  const sorted = [...rows].sort((a, b) => {
    if (a.fiscal_year !== b.fiscal_year) return a.fiscal_year - b.fiscal_year;
    return (a.fiscal_quarter || 0) - (b.fiscal_quarter || 0);
  });

  return sorted.map((row) => {
    const point = {
      period: row.fiscal_quarter
        ? `${row.fiscal_year} Q${row.fiscal_quarter}`
        : String(row.fiscal_year),
    };
    chartKeys.forEach(({ key, label }) => {
      const val = toMillions(row[key]);
      point[label] = val;
    });
    return point;
  });
}

/**
 * Line chart showing trend of key metrics from a financial statement.
 */
function TrendChart({ rows, chartKeys, title }) {
  const data = buildChartData(rows, chartKeys);

  // Only show lines that have at least one non-null value
  const activeKeys = chartKeys.filter(({ label }) =>
    data.some((d) => d[label] !== null && d[label] !== undefined)
  );

  if (data.length === 0 || activeKeys.length === 0) return null;

  return (
    <Box sx={{ mt: 4 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1, color: "text.secondary" }}>
        {title} — Trend ($ Millions)
      </Typography>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 8, right: 24, left: 16, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
          <XAxis dataKey="period" tick={{ fontSize: 11 }} />
          <YAxis
            tickFormatter={(v) => {
              if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}B`;
              return `$${v}M`;
            }}
            tick={{ fontSize: 11 }}
            width={72}
          />
          <Tooltip
            formatter={tooltipFormatter}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {activeKeys.map(({ label }, i) => (
            <Line
              key={label}
              type="monotone"
              dataKey={label}
              stroke={CHART_COLORS[i % CHART_COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Box>
  );
}

/**
 * Bar chart variant — good for cash flows where values can be negative.
 */
function TrendBarChart({ rows, chartKeys, title }) {
  const data = buildChartData(rows, chartKeys);

  const activeKeys = chartKeys.filter(({ label }) =>
    data.some((d) => d[label] !== null && d[label] !== undefined)
  );

  if (data.length === 0 || activeKeys.length === 0) return null;

  return (
    <Box sx={{ mt: 4 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1, color: "text.secondary" }}>
        {title} — Trend ($ Millions)
      </Typography>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 8, right: 24, left: 16, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
          <XAxis dataKey="period" tick={{ fontSize: 11 }} />
          <YAxis
            tickFormatter={(v) => {
              if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}B`;
              return `$${v}M`;
            }}
            tick={{ fontSize: 11 }}
            width={72}
          />
          <Tooltip
            formatter={tooltipFormatter}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {activeKeys.map(({ label }, i) => (
            <Bar
              key={label}
              dataKey={label}
              fill={CHART_COLORS[i % CHART_COLORS.length]}
              maxBarSize={40}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </Box>
  );
}

// ─── main page ───────────────────────────────────────────────────────────────

function FinancialData() {
  const [searchParams] = useSearchParams();
  const urlSymbol = searchParams.get("symbol");

  const [ticker, setTicker] = useState(urlSymbol || "AAPL");
  const [tabValue, setTabValue] = useState(0);
  const [period, setPeriod] = useState("annual");

  // ── data queries ──────────────────────────────────────────────────────────

  const { data: companiesData, isLoading: companiesLoading } = useQuery({
    queryKey: ["companies"],
    queryFn: () => getStocks({ limit: 1000 }),
    staleTime: 5 * 60 * 1000,
  });

  const { data: balanceSheetData, isLoading: bsLoading } = useQuery({
    queryKey: ["balance-sheet", ticker, period],
    queryFn: () => getBalanceSheet(ticker, period),
    enabled: !!ticker,
  });

  const { data: incomeStatementData, isLoading: isLoading } = useQuery({
    queryKey: ["income-statement", ticker, period],
    queryFn: () => getIncomeStatement(ticker, period),
    enabled: !!ticker,
  });

  const { data: cashFlowData, isLoading: cfLoading } = useQuery({
    queryKey: ["cash-flow", ticker, period],
    queryFn: () => getCashFlowStatement(ticker, period),
    enabled: !!ticker,
  });

  const { data: keyMetricsData, isLoading: kmLoading } = useQuery({
    queryKey: ["key-metrics", ticker],
    queryFn: () => getKeyMetrics(ticker),
    enabled: !!ticker,
  });

  // ── helpers ───────────────────────────────────────────────────────────────

  const getFinancialData = (data) => data?.data?.financialData || [];

  const companies = Array.isArray(companiesData?.data) ? companiesData.data : [];

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
          Financial Data
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 3 }}>
          Comprehensive financial statements and trend charts
        </Typography>

        {/* ── Controls ── */}
        <Card sx={{ mb: 3, backgroundColor: "#fafafa" }}>
          <CardContent>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} md={6}>
                <Autocomplete
                  options={companies}
                  getOptionLabel={(option) =>
                    `${option.ticker || option.symbol} — ${option.short_name || option.name || ""}`
                  }
                  value={
                    companies.find((c) => (c.ticker || c.symbol) === ticker) || null
                  }
                  onChange={(_, newValue) => {
                    if (newValue) setTicker(newValue.ticker || newValue.symbol);
                  }}
                  loading={companiesLoading}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Select Company"
                      placeholder="Search by ticker or name"
                    />
                  )}
                />
              </Grid>
              <Grid item xs={12} md={3}>
                <ToggleButtonGroup
                  value={period}
                  exclusive
                  onChange={(_, v) => { if (v !== null) setPeriod(v); }}
                  size="small"
                  fullWidth
                >
                  <ToggleButton value="annual" sx={{ flex: 1 }}>Annual</ToggleButton>
                  <ToggleButton value="quarterly" sx={{ flex: 1 }}>Quarterly</ToggleButton>
                </ToggleButtonGroup>
              </Grid>
              <Grid item xs={12} md={3}>
                <Typography variant="body2" color="text.secondary">
                  Showing <strong>{period}</strong> data for{" "}
                  <strong>{ticker}</strong>
                </Typography>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* ── Tabs ── */}
        <Paper sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
          <Tabs
            value={tabValue}
            onChange={(_, v) => setTabValue(v)}
            aria-label="financial statements"
            sx={{ backgroundColor: "#fafafa" }}
          >
            <Tab label="Balance Sheet" />
            <Tab label="Income Statement" />
            <Tab label="Cash Flow" />
            <Tab label="Key Metrics" />
          </Tabs>
        </Paper>

        {/* ── Balance Sheet ── */}
        {tabValue === 0 && (
          <Box>
            {bsLoading ? (
              <CircularProgress />
            ) : getFinancialData(balanceSheetData).length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Balance Sheet — {ticker}
                  </Typography>
                  <FinancialTable rows={getFinancialData(balanceSheetData)} />
                  <Divider sx={{ my: 3 }} />
                  <TrendChart
                    rows={getFinancialData(balanceSheetData)}
                    chartKeys={BALANCE_CHART_KEYS}
                    title="Balance Sheet"
                  />
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No balance sheet data available for {ticker}.</Alert>
            )}
          </Box>
        )}

        {/* ── Income Statement ── */}
        {tabValue === 1 && (
          <Box>
            {isLoading ? (
              <CircularProgress />
            ) : getFinancialData(incomeStatementData).length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Income Statement — {ticker}
                  </Typography>
                  <FinancialTable rows={getFinancialData(incomeStatementData)} />
                  <Divider sx={{ my: 3 }} />
                  <TrendChart
                    rows={getFinancialData(incomeStatementData)}
                    chartKeys={INCOME_CHART_KEYS}
                    title="Income Statement"
                  />
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No income statement data available for {ticker}.</Alert>
            )}
          </Box>
        )}

        {/* ── Cash Flow ── */}
        {tabValue === 2 && (
          <Box>
            {cfLoading ? (
              <CircularProgress />
            ) : getFinancialData(cashFlowData).length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Cash Flow Statement — {ticker}
                  </Typography>
                  <FinancialTable rows={getFinancialData(cashFlowData)} />
                  <Divider sx={{ my: 3 }} />
                  <TrendBarChart
                    rows={getFinancialData(cashFlowData)}
                    chartKeys={CASHFLOW_CHART_KEYS}
                    title="Cash Flow"
                  />
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No cash flow data available for {ticker}.</Alert>
            )}
          </Box>
        )}

        {/* ── Key Metrics ── */}
        {tabValue === 3 && (
          <Box>
            {kmLoading ? (
              <CircularProgress />
            ) : keyMetricsData?.data ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
                    Key Metrics — {ticker}
                  </Typography>
                  {keyMetricsData.data.name && (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                      {keyMetricsData.data.name}
                      {keyMetricsData.data.sector
                        ? ` · ${keyMetricsData.data.sector}`
                        : ""}
                      {keyMetricsData.data.industry
                        ? ` · ${keyMetricsData.data.industry}`
                        : ""}
                    </Typography>
                  )}

                  <Grid container spacing={2}>
                    {[
                      { label: "P/E Ratio",            value: keyMetricsData.data.pe_ratio,              fmt: "ratio" },
                      { label: "Forward P/E",          value: keyMetricsData.data.forward_pe,            fmt: "ratio" },
                      { label: "P/B Ratio",            value: keyMetricsData.data.pb_ratio,              fmt: "ratio" },
                      { label: "P/S Ratio",            value: keyMetricsData.data.ps_ratio,              fmt: "ratio" },
                      { label: "PEG Ratio",            value: keyMetricsData.data.peg_ratio,             fmt: "ratio" },
                      { label: "EV / Revenue",         value: keyMetricsData.data.ev_to_revenue,         fmt: "ratio" },
                      { label: "EV / EBITDA",          value: keyMetricsData.data.ev_to_ebitda,          fmt: "ratio" },
                      { label: "Dividend Yield",       value: keyMetricsData.data.dividend_yield,        fmt: "pct_decimal" },
                      { label: "Payout Ratio",         value: keyMetricsData.data.payout_ratio,          fmt: "pct_decimal" },
                      { label: "Debt / Equity",        value: keyMetricsData.data.debt_to_equity,        fmt: "ratio" },
                      { label: "Current Ratio",        value: keyMetricsData.data.current_ratio,         fmt: "ratio" },
                      { label: "Quick Ratio",          value: keyMetricsData.data.quick_ratio,           fmt: "ratio" },
                      { label: "ROE %",                value: keyMetricsData.data.roe,                   fmt: "ratio" },
                      { label: "ROA %",                value: keyMetricsData.data.roa,                   fmt: "ratio" },
                      { label: "Gross Margin %",       value: keyMetricsData.data.gross_margin,          fmt: "ratio" },
                      { label: "Operating Margin %",   value: keyMetricsData.data.operating_margin,      fmt: "ratio" },
                      { label: "Profit Margin %",      value: keyMetricsData.data.profit_margin,         fmt: "ratio" },
                      { label: "Insider Ownership",    value: keyMetricsData.data.insider_ownership,     fmt: "pct_decimal" },
                      { label: "Institutional Own.",   value: keyMetricsData.data.institutional_ownership, fmt: "pct_decimal" },
                    ]
                      .filter((m) => m.value != null)
                      .map(({ label, value, fmt }) => {
                        const num = parseFloat(value);
                        let display;
                        if (fmt === "pct_decimal") {
                          // Values may be decimals (0.03) or already percents (3.0)
                          display = Math.abs(num) < 1
                            ? `${(num * 100).toFixed(2)}%`
                            : `${num.toFixed(2)}%`;
                        } else {
                          display = isNaN(num) ? String(value) : num.toFixed(2);
                        }
                        return (
                          <Grid item xs={6} sm={4} md={3} key={label}>
                            <Paper
                              sx={{
                                p: 2,
                                backgroundColor: "#f5f5f5",
                                height: "100%",
                              }}
                            >
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                display="block"
                              >
                                {label}
                              </Typography>
                              <Typography
                                variant="h6"
                                sx={{ fontSize: "1rem", fontWeight: 700 }}
                              >
                                {display}
                              </Typography>
                            </Paper>
                          </Grid>
                        );
                      })}
                  </Grid>

                  {!keyMetricsData.data.pe_ratio &&
                    !keyMetricsData.data.debt_to_equity &&
                    !keyMetricsData.data.current_ratio &&
                    !keyMetricsData.data.gross_margin &&
                    !keyMetricsData.data.roe && (
                      <Alert severity="info" sx={{ mt: 2 }}>
                        Financial ratio data not yet loaded for {ticker}. Income
                        and Cash Flow tabs may have available data.
                      </Alert>
                    )}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">
                No key metrics data available for {ticker}.
              </Alert>
            )}
          </Box>
        )}
      </Box>
    </Container>
  );
}

export default FinancialData;
