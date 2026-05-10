import { useState } from "react";
import { useApiQuery } from "../hooks/useApiQuery";
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
  ToggleButton,
  ToggleButtonGroup,
  List,
  ListItem,
  ListItemText,
  Divider,
} from "@mui/material";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { getStocks, getBalanceSheet, getIncomeStatement, getCashFlowStatement, getKeyMetrics } from "../services/api";
import { formatCurrency } from "../utils/formatters";

function FinancialData() {
  const [ticker, setTicker] = useState("AAPL");
  const [tabValue, setTabValue] = useState(0);
  const [period, setPeriod] = useState("annual");

  // Get companies list
  const { data: companiesData, loading: companiesLoading, error: companiesError, refetch: refetchCompanies } = useApiQuery(
    ["companies"],
    () => getStocks({ limit: 1000 }),
    { staleTime: 5 * 60 * 1000 }
  );

  const companies = companiesData?.data ?? [];
  const safeCompanies = Array.isArray(companies) ? companies : [];

  // Get financial data with period selection
  const { data: balanceSheetData, loading: bsLoading, error: bsError, refetch: refetchBS } = useApiQuery(
    ["balance-sheet", ticker, period],
    () => getBalanceSheet(ticker, period),
    { enabled: !!ticker }
  );

  const { data: incomeStatementData, loading: isLoading, error: isError, refetch: refetchIS } = useApiQuery(
    ["income-statement", ticker, period],
    () => getIncomeStatement(ticker, period),
    { enabled: !!ticker }
  );

  const { data: cashFlowData, loading: cfLoading, error: cfError, refetch: refetchCF } = useApiQuery(
    ["cash-flow", ticker, period],
    () => getCashFlowStatement(ticker, period),
    { enabled: !!ticker }
  );

  const { data: keyMetricsData, loading: kmLoading, error: kmError, refetch: refetchKM } = useApiQuery(
    ["key-metrics", ticker],
    () => getKeyMetrics(ticker),
    { enabled: !!ticker }
  );

  const getFinancialData = (data) => {
    return data?.data?.financialData || [];
  };

  // Format field name for display (snake_case -> Title Case)
  const formatFieldName = (field) => {
    return field
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Get all available financial fields (excluding metadata)
  const getAvailableFields = (rows) => {
    if (!rows || rows.length === 0) return [];
    const fieldsSet = new Set();
    rows.forEach(row => {
      Object.keys(row).forEach(key => {
        if (!['id', 'date', 'symbol'].includes(key)) {
          fieldsSet.add(key);
        }
      });
    });

    // Sort with priority fields first
    const priority = ['fiscal_year', 'total_assets', 'total_liabilities', 'stockholders_equity',
                     'revenue', 'gross_profit', 'operating_income', 'net_income',
                     'operating_cash_flow', 'investing_cash_flow', 'financing_cash_flow'];
    const fields = Array.from(fieldsSet);
    return [
      ...priority.filter(f => fields.includes(f)),
      ...fields.filter(f => !priority.includes(f)).sort()
    ];
  };

  // Render complete financial statement as list
  const renderFinancialList = (rows) => {
    if (!rows || rows.length === 0) {
      return <Alert severity="info">No data available for selected period</Alert>;
    }

    const fields = getAvailableFields(rows);

    return (
      <Box>
        {rows.map((row, idx) => (
          <Card key={idx} sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                {period === 'annual' ? `FY ${row.fiscal_year}` : `Q${row.fiscal_quarter} ${row.fiscal_year}`}
              </Typography>
              <List sx={{ width: '100%' }}>
                {fields.map((field, fidx) => (
                  <Box key={field}>
                    <ListItem sx={{ py: 1, px: 0 }}>
                      <ListItemText
                        primary={formatFieldName(field)}
                        secondary={
                          typeof row[field] === 'number' ?
                            formatCurrency(row[field]) :
                            (row[field] ? String(row[field]) : '—')
                        }
                        primaryTypographyProps={{ variant: 'body2', sx: { fontWeight: 500 } }}
                        secondaryTypographyProps={{ variant: 'body2', sx: { fontWeight: 600, color: 'primary.main' } }}
                      />
                    </ListItem>
                    {fidx < fields.length - 1 && <Divider />}
                  </Box>
                ))}
              </List>
            </CardContent>
          </Card>
        ))}

        {/* Trend Chart */}
        {rows.length > 1 && (
          <Card sx={{ mt: 4 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 3, fontWeight: 600 }}>
                Trend Analysis
              </Typography>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={rows.map(row => ({
                  period: `FY${row.fiscal_year}`,
                  assets: row.total_assets,
                  revenue: row.revenue,
                  income: row.net_income,
                }))} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" />
                  <YAxis />
                  <Tooltip formatter={(value) => value ? formatCurrency(value) : '—'} />
                  <Legend />
                  {rows.some(r => r.total_assets) && <Line type="monotone" dataKey="assets" stroke="#8884d8" name="Total Assets" />}
                  {rows.some(r => r.revenue) && <Line type="monotone" dataKey="revenue" stroke="#82ca9d" name="Revenue" />}
                  {rows.some(r => r.net_income) && <Line type="monotone" dataKey="income" stroke="#ffc658" name="Net Income" />}
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        )}
      </Box>
    );
  };

  // Check for critical errors
  const criticalErrors = [companiesError];
  const hasCompaniesError = criticalErrors.some(err => err);

  if (hasCompaniesError) {
    return (
      <Container maxWidth="xl">
        <Box sx={{ py: 3 }}>
          <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
            📊 Financial Data Analysis
          </Typography>
          <Alert severity="error" sx={{ mt: 2, mb: 2 }}>
            <Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1 }}>
                Failed to load financial data
              </Typography>
              <Typography variant="body2" sx={{ mb: 2 }}>
                {companiesError && 'Companies list unavailable'}
              </Typography>
              <button
                onClick={() => {
                  companiesError && refetchCompanies?.();
                }}
                style={{
                  padding: '8px 16px',
                  backgroundColor: '#d32f2f',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: 'pointer',
                }}
              >
                Retry
              </button>
            </Box>
          </Alert>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 3 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
          📊 Financial Data Analysis
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 4 }}>
          Complete financial statements with trend analysis
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
            {bsError ? (
              <Alert severity="error" action={<button onClick={() => refetchBS?.()}>Retry</button>}>
                Failed to load balance sheet data for {ticker}
              </Alert>
            ) : bsLoading ? (
              <CircularProgress />
            ) : getFinancialData(balanceSheetData).length > 0 ? (
              <Box>
                <Typography variant="h5" sx={{ mb: 3, fontWeight: 600 }}>
                  Balance Sheet - {ticker}
                </Typography>
                {renderFinancialList(getFinancialData(balanceSheetData))}
              </Box>
            ) : (
              <Alert severity="warning">No balance sheet data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {/* Income Statement */}
        {tabValue === 1 && (
          <Box>
            {isError ? (
              <Alert severity="error" action={<button onClick={() => refetchIS?.()}>Retry</button>}>
                Failed to load income statement data for {ticker}
              </Alert>
            ) : isLoading ? (
              <CircularProgress />
            ) : getFinancialData(incomeStatementData).length > 0 ? (
              <Box>
                <Typography variant="h5" sx={{ mb: 3, fontWeight: 600 }}>
                  Income Statement - {ticker}
                </Typography>
                {renderFinancialList(getFinancialData(incomeStatementData))}
              </Box>
            ) : (
              <Alert severity="warning">No income statement data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {/* Cash Flow */}
        {tabValue === 2 && (
          <Box>
            {cfError ? (
              <Alert severity="error" action={<button onClick={() => refetchCF?.()}>Retry</button>}>
                Failed to load cash flow data for {ticker}
              </Alert>
            ) : cfLoading ? (
              <CircularProgress />
            ) : getFinancialData(cashFlowData).length > 0 ? (
              <Box>
                <Typography variant="h5" sx={{ mb: 3, fontWeight: 600 }}>
                  Cash Flow Statement - {ticker}
                </Typography>
                {renderFinancialList(getFinancialData(cashFlowData))}
              </Box>
            ) : (
              <Alert severity="warning">No cash flow data available for {ticker}</Alert>
            )}
          </Box>
        )}

        {/* Key Metrics */}
        {tabValue === 3 && (
          <Box>
            {kmError ? (
              <Alert severity="error" action={<button onClick={() => refetchKM?.()}>Retry</button>}>
                Failed to load key metrics for {ticker}
              </Alert>
            ) : kmLoading ? (
              <CircularProgress />
            ) : keyMetricsData?.data ? (
              <Card>
                <CardContent>
                  <Typography variant="h5" sx={{ mb: 3, fontWeight: 600 }}>
                    Key Metrics - {ticker}
                  </Typography>
                  <Grid container spacing={3}>
                    {Object.entries(keyMetricsData.data).map(([key, value]) => (
                      value !== null && value !== undefined && (
                        <Grid item xs={12} sm={6} md={4} key={key}>
                          <Paper sx={{ p: 2, backgroundColor: "#f5f5f5" }}>
                            <Typography variant="caption" color="text.secondary">
                              {formatFieldName(key)}
                            </Typography>
                            <Typography variant="h6" sx={{ mt: 1 }}>
                              {typeof value === 'number' && Math.abs(value) < 1 && key.includes('yield')
                                ? `${(value * 100).toFixed(2)}%`
                                : typeof value === 'number'
                                ? formatCurrency(value)
                                : String(value)}
                            </Typography>
                          </Paper>
                        </Grid>
                      )
                    ))}
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
