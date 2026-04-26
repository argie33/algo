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

  // Get companies list
  const { data: companiesData, isLoading: companiesLoading } = useQuery({
    queryKey: ["companies"],
    queryFn: () => getStocks({ limit: 1000 }),
    staleTime: 5 * 60 * 1000,
  });

  const companies = companiesData?.data ?? [];
  const safeCompanies = Array.isArray(companies) ? companies : [];

  // Get financial data with period selection
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

  // Helper to safely extract financial data
  const getFinancialData = (data) => {
    return data?.data?.financialData || [];
  };

  // Render financial table
  const renderFinancialTable = (rows, columns) => {
    if (!rows || rows.length === 0) {
      return <Alert severity="info">No data available for selected period</Alert>;
    }

    return (
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
              <TableCell sx={{ fontWeight: "bold" }}>Fiscal Year</TableCell>
              {columns.map((col) => (
                <TableCell key={col.key} align="right" sx={{ fontWeight: "bold" }}>
                  {col.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((row, idx) => (
              <TableRow key={idx} sx={{ "&:hover": { backgroundColor: "#f9f9f9" } }}>
                <TableCell sx={{ fontWeight: "500" }}>{row.fiscal_year}</TableCell>
                {columns.map((col) => (
                  <TableCell key={col.key} align="right">
                    {row[col.key] ? formatCurrency(row[col.key]) : "—"}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
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

        {/* Company Selection */}
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

        {/* Tabs */}
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

        {/* Balance Sheet */}
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
                  {renderFinancialTable(getFinancialData(balanceSheetData), [
                    { key: "total_assets", label: "Total Assets" },
                    { key: "total_liabilities", label: "Total Liabilities" },
                    { key: "stockholders_equity", label: "Stockholders Equity" },
                  ])}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No balance sheet data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {/* Income Statement */}
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
                  {renderFinancialTable(getFinancialData(incomeStatementData), [
                    { key: "revenue", label: "Revenue" },
                    { key: "gross_profit", label: "Gross Profit" },
                    { key: "operating_income", label: "Operating Income" },
                    { key: "net_income", label: "Net Income" },
                  ])}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No income statement data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {/* Cash Flow */}
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
                  {renderFinancialTable(getFinancialData(cashFlowData), [
                    { key: "operating_cash_flow", label: "Operating Cash Flow" },
                    { key: "investing_cash_flow", label: "Investing Cash Flow" },
                    { key: "financing_cash_flow", label: "Financing Cash Flow" },
                  ])}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="warning">No cash flow data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {/* Key Metrics */}
        {tabValue === 3 && (
          <Box>
            {kmLoading ? (
              <CircularProgress />
            ) : keyMetricsData?.data ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                    Key Metrics - {ticker}
                  </Typography>
                  <Grid container spacing={3}>
                    {keyMetricsData.data.pe_ratio && (
                      <Grid item xs={12} sm={6} md={3}>
                        <Paper sx={{ p: 2, backgroundColor: "#f5f5f5" }}>
                          <Typography variant="caption" color="text.secondary">
                            P/E Ratio
                          </Typography>
                          <Typography variant="h6">{keyMetricsData.data.pe_ratio}</Typography>
                        </Paper>
                      </Grid>
                    )}
                    {keyMetricsData.data.dividend_yield && (
                      <Grid item xs={12} sm={6} md={3}>
                        <Paper sx={{ p: 2, backgroundColor: "#f5f5f5" }}>
                          <Typography variant="caption" color="text.secondary">
                            Dividend Yield
                          </Typography>
                          <Typography variant="h6">
                            {(parseFloat(keyMetricsData.data.dividend_yield) * 100).toFixed(2)}%
                          </Typography>
                        </Paper>
                      </Grid>
                    )}
                    {keyMetricsData.data.debt_to_equity && (
                      <Grid item xs={12} sm={6} md={3}>
                        <Paper sx={{ p: 2, backgroundColor: "#f5f5f5" }}>
                          <Typography variant="caption" color="text.secondary">
                            Debt/Equity
                          </Typography>
                          <Typography variant="h6">{keyMetricsData.data.debt_to_equity}</Typography>
                        </Paper>
                      </Grid>
                    )}
                    {keyMetricsData.data.current_ratio && (
                      <Grid item xs={12} sm={6} md={3}>
                        <Paper sx={{ p: 2, backgroundColor: "#f5f5f5" }}>
                          <Typography variant="caption" color="text.secondary">
                            Current Ratio
                          </Typography>
                          <Typography variant="h6">{keyMetricsData.data.current_ratio}</Typography>
                        </Paper>
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
