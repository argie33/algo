import { useState } from "react";
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
} from "@mui/material";
import { getStocks, getBalanceSheet, getIncomeStatement, getCashFlowStatement, getKeyMetrics } from "../services/api";
import { formatCurrency } from "../utils/formatters";

function FinancialData() {
  const [ticker, setTicker] = useState("AAPL");
  const [tabValue, setTabValue] = useState(0);
  const [period, setPeriod] = useState("annual");

  const { data: companiesData, isLoading: companiesLoading } = useQuery({
    queryKey: ["companies"],
    queryFn: () => getStocks({ limit: 1000 }),
    staleTime: 5 * 60 * 1000,
  });

  const companies = companiesData?.data ?? [];
  const safeCompanies = Array.isArray(companies) ? companies : [];

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

  const getFinancialData = (data) => {
    return data?.data?.financialData || [];
  };

  const EXCLUDED_KEYS = new Set(['id', 'symbol', 'fiscal_year', 'fiscal_quarter', 'created_at', 'updated_at', 'fetched_at']);

  const formatColHeader = (key) =>
    key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  const formatCellVal = (value) => {
    if (value === null || value === undefined || value === '') return '—';
    const num = parseFloat(value);
    if (isNaN(num)) return String(value);
    if (Math.abs(num) >= 1000) return formatCurrency(num);
    return num.toFixed(2);
  };

  const renderFinancialTable = (rows) => {
    if (!rows || rows.length === 0) {
      return <Alert severity="info">No data available for selected period</Alert>;
    }

    const allKeys = Object.keys(rows[0]).filter(k => !EXCLUDED_KEYS.has(k));

    return (
      <Box sx={{ overflowX: 'auto' }}>
        <TableContainer component={Paper} sx={{ maxHeight: 600 }}>
          <Table stickyHeader size="small">
            <TableHead>
              <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                <TableCell sx={{ fontWeight: "bold", minWidth: 100, position: 'sticky', left: 0, zIndex: 3, backgroundColor: '#f5f5f5' }}>Fiscal Year</TableCell>
                {allKeys.map((key) => (
                  <TableCell key={key} align="right" sx={{ fontWeight: "bold", whiteSpace: 'nowrap', minWidth: 140 }}>
                    {formatColHeader(key)}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, idx) => (
                <TableRow key={idx} sx={{ "&:hover": { backgroundColor: "#f9f9f9" } }}>
                  <TableCell sx={{ fontWeight: "500", position: 'sticky', left: 0, backgroundColor: idx % 2 === 0 ? '#ffffff' : '#f9f9f9', zIndex: 1 }}>
                    {row.fiscal_year}{row.fiscal_quarter ? ` Q${row.fiscal_quarter}` : ''}
                  </TableCell>
                  {allKeys.map((key) => (
                    <TableCell key={key} align="right" sx={{ whiteSpace: 'nowrap' }}>
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
  };

  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 3 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
          📊 Financial Data Analysis
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 4 }}>
          Comprehensive financial statements for stocks
        </Typography>

        <Card sx={{ mb: 3, backgroundColor: "#fafafa" }}>
          <CardContent>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} md={6}>
                <Autocomplete
                  options={safeCompanies}
                  getOptionLabel={(option) => `${option.ticker || option.symbol} - ${option.short_name || option.name || ""}`}
                  value={safeCompanies.find((c) => (c.ticker || c.symbol) === ticker) || null}
                  onChange={(_, newValue) => {
                    if (newValue) setTicker(newValue.ticker || newValue.symbol);
                  }}
                  loading={companiesLoading}
                  renderInput={(params) => <TextField {...params} label="Select Company" placeholder="Search by ticker or name" />}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <ToggleButtonGroup
                  value={period}
                  exclusive
                  onChange={(_, newPeriod) => {
                    if (newPeriod !== null) setPeriod(newPeriod);
                  }}
                  size="small"
                  fullWidth
                >
                  <ToggleButton value="annual" sx={{ flex: 1 }}>
                    Annual
                  </ToggleButton>
                  <ToggleButton value="quarterly" sx={{ flex: 1 }}>
                    Quarterly
                  </ToggleButton>
                </ToggleButtonGroup>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

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

        {tabValue === 0 && (
          <Box>
            {bsLoading ? (
              <CircularProgress />
            ) : getFinancialData(balanceSheetData).length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                    Balance Sheet - {ticker}
                  </Typography>
                  {renderFinancialTable(getFinancialData(balanceSheetData))}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No balance sheet data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {tabValue === 1 && (
          <Box>
            {isLoading ? (
              <CircularProgress />
            ) : getFinancialData(incomeStatementData).length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                    Income Statement - {ticker}
                  </Typography>
                  {renderFinancialTable(getFinancialData(incomeStatementData))}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No income statement data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {tabValue === 2 && (
          <Box>
            {cfLoading ? (
              <CircularProgress />
            ) : getFinancialData(cashFlowData).length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                    Cash Flow Statement - {ticker}
                  </Typography>
                  {renderFinancialTable(getFinancialData(cashFlowData))}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No cash flow data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {tabValue === 3 && (
          <Box>
            {kmLoading ? (
              <CircularProgress />
            ) : keyMetricsData?.data ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 1, fontWeight: 600 }}>
                    Key Metrics - {ticker}
                  </Typography>
                  {keyMetricsData.data.name && (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                      {keyMetricsData.data.name} · {keyMetricsData.data.sector} · {keyMetricsData.data.industry}
                    </Typography>
                  )}
                  <Grid container spacing={2}>
                    {[
                      { label: "P/E Ratio", value: keyMetricsData.data.pe_ratio, format: "number" },
                      { label: "Forward P/E", value: keyMetricsData.data.forward_pe, format: "number" },
                      { label: "P/B Ratio", value: keyMetricsData.data.pb_ratio, format: "number" },
                      { label: "P/S Ratio", value: keyMetricsData.data.ps_ratio, format: "number" },
                      { label: "EV/EBITDA", value: keyMetricsData.data.ev_to_ebitda, format: "number" },
                      { label: "PEG Ratio", value: keyMetricsData.data.peg_ratio, format: "number" },
                      { label: "Dividend Yield", value: keyMetricsData.data.dividend_yield, format: "percent" },
                      { label: "Debt/Equity", value: keyMetricsData.data.debt_to_equity, format: "number" },
                      { label: "Current Ratio", value: keyMetricsData.data.current_ratio, format: "number" },
                      { label: "Quick Ratio", value: keyMetricsData.data.quick_ratio, format: "number" },
                      { label: "ROE %", value: keyMetricsData.data.roe, format: "number" },
                      { label: "ROA %", value: keyMetricsData.data.roa, format: "number" },
                      { label: "Gross Margin %", value: keyMetricsData.data.gross_margin, format: "number" },
                      { label: "Operating Margin %", value: keyMetricsData.data.operating_margin, format: "number" },
                      { label: "Profit Margin %", value: keyMetricsData.data.profit_margin, format: "number" },
                      { label: "Insider Ownership", value: keyMetricsData.data.insider_ownership, format: "percent" },
                      { label: "Institutional Own.", value: keyMetricsData.data.institutional_ownership, format: "percent" },
                    ].filter(m => m.value != null).map(({ label, value, format }) => (
                      <Grid item xs={6} sm={4} md={3} key={label}>
                        <Paper sx={{ p: 2, backgroundColor: "#f5f5f5" }}>
                          <Typography variant="caption" color="text.secondary" display="block">{label}</Typography>
                          <Typography variant="h6" sx={{ fontSize: "1rem" }}>
                            {format === "percent"
                              ? `${(parseFloat(value) * (Math.abs(parseFloat(value)) < 1 ? 100 : 1)).toFixed(2)}%`
                              : parseFloat(value).toFixed(2)}
                          </Typography>
                        </Paper>
                      </Grid>
                    ))}
                    {!keyMetricsData.data.pe_ratio && !keyMetricsData.data.debt_to_equity && !keyMetricsData.data.current_ratio && !keyMetricsData.data.gross_margin && !keyMetricsData.data.roe && (
                      <Grid item xs={12}>
                        <Alert severity="info">Financial ratio data not yet loaded for {ticker}. Income &amp; Cash Flow tabs have available data.</Alert>
                      </Grid>
                    )}
                  </Grid>
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No key metrics data available for {ticker}</Alert>
            )}
          </Box>
        )}
      </Box>
    </Container>
  );
}

export default FinancialData;
