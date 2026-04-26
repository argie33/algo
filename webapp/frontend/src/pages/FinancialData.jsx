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
} from "@mui/material";
import { getStocks, getBalanceSheet, getIncomeStatement, getCashFlowStatement, getKeyMetrics } from "../services/api";

function FinancialData() {
  const [ticker, setTicker] = useState("AAPL");
  const [tabValue, setTabValue] = useState(0);

  // Get companies list
  const { data: companiesData } = useQuery({
    queryKey: ["companies"],
    queryFn: () => getStocks({ limit: 1000 }),
  });

  const companies = companiesData?.data ?? [];
  const safeCompanies = Array.isArray(companies) ? companies : [];

  // Get financial data
  const { data: balanceSheetData, isLoading: bsLoading } = useQuery({
    queryKey: ["balance-sheet", ticker],
    queryFn: () => getBalanceSheet(ticker),
    enabled: !!ticker,
  });

  const { data: incomeStatementData, isLoading: isLoading } = useQuery({
    queryKey: ["income-statement", ticker],
    queryFn: () => getIncomeStatement(ticker),
    enabled: !!ticker,
  });

  const { data: cashFlowData, isLoading: cfLoading } = useQuery({
    queryKey: ["cash-flow", ticker],
    queryFn: () => getCashFlowStatement(ticker),
    enabled: !!ticker,
  });

  const { data: keyMetricsData, isLoading: kmLoading } = useQuery({
    queryKey: ["key-metrics", ticker],
    queryFn: () => getKeyMetrics(ticker),
    enabled: !!ticker,
  });

  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 3 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
          📊 Financial Data Analysis
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 3 }}>
          Comprehensive financial statements for stocks
        </Typography>

        {/* Company Selection */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <Autocomplete
                  options={safeCompanies}
                  getOptionLabel={(option) => `${option.ticker} - ${option.short_name || ""}`}
                  value={safeCompanies.find((c) => c.ticker === ticker) || null}
                  onChange={(_, newValue) => {
                    if (newValue) setTicker(newValue.ticker);
                  }}
                  renderInput={(params) => <TextField {...params} label="Select Company" />}
                />
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Tabs */}
        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
          <Tabs value={tabValue} onChange={(_, v) => setTabValue(v)}>
            <Tab label="Balance Sheet" />
            <Tab label="Income Statement" />
            <Tab label="Cash Flow" />
            <Tab label="Key Metrics" />
          </Tabs>
        </Box>

        {/* Tab Content */}
        {tabValue === 0 && (
          <Box>
            {bsLoading ? (
              <CircularProgress />
            ) : balanceSheetData?.data?.financialData?.length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2 }}>Balance Sheet - {ticker}</Typography>
                  {balanceSheetData.data.financialData.map((item, idx) => (
                    <Box key={idx} sx={{ mb: 3, pb: 2, borderBottom: idx < balanceSheetData.data.financialData.length - 1 ? '1px solid #ddd' : 'none' }}>
                      <Typography variant="subtitle2">Fiscal Year: {item.fiscal_year}</Typography>
                      <Grid container spacing={2} sx={{ mt: 1 }}>
                        <Grid item xs={12} sm={6}><Typography>Total Assets: ${parseFloat(item.total_assets || 0).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>
                        <Grid item xs={12} sm={6}><Typography>Total Liabilities: ${parseFloat(item.total_liabilities || 0).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>
                        {item.stockholders_equity && <Grid item xs={12} sm={6}><Typography>Equity: ${parseFloat(item.stockholders_equity).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>}
                      </Grid>
                    </Box>
                  ))}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="info">No balance sheet data available</Alert>
            )}
          </Box>
        )}

        {tabValue === 1 && (
          <Box>
            {isLoading ? (
              <CircularProgress />
            ) : incomeStatementData?.data?.financialData?.length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2 }}>Income Statement - {ticker}</Typography>
                  {incomeStatementData.data.financialData.map((item, idx) => (
                    <Box key={idx} sx={{ mb: 3, pb: 2, borderBottom: idx < incomeStatementData.data.financialData.length - 1 ? '1px solid #ddd' : 'none' }}>
                      <Typography variant="subtitle2">Fiscal Year: {item.fiscal_year}</Typography>
                      <Grid container spacing={2} sx={{ mt: 1 }}>
                        <Grid item xs={12} sm={6}><Typography>Revenue: ${parseFloat(item.revenue || 0).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>
                        <Grid item xs={12} sm={6}><Typography>Net Income: ${parseFloat(item.net_income || 0).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>
                        {item.gross_profit && <Grid item xs={12} sm={6}><Typography>Gross Profit: ${parseFloat(item.gross_profit).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>}
                        {item.operating_income && <Grid item xs={12} sm={6}><Typography>Operating Income: ${parseFloat(item.operating_income).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>}
                      </Grid>
                    </Box>
                  ))}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="info">No income statement data available</Alert>
            )}
          </Box>
        )}

        {tabValue === 2 && (
          <Box>
            {cfLoading ? (
              <CircularProgress />
            ) : cashFlowData?.data?.financialData?.length > 0 ? (
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2 }}>Cash Flow - {ticker}</Typography>
                  {cashFlowData.data.financialData.map((item, idx) => (
                    <Box key={idx} sx={{ mb: 3, pb: 2, borderBottom: idx < cashFlowData.data.financialData.length - 1 ? '1px solid #ddd' : 'none' }}>
                      <Typography variant="subtitle2">Fiscal Year: {item.fiscal_year}</Typography>
                      <Grid container spacing={2} sx={{ mt: 1 }}>
                        <Grid item xs={12} sm={6}><Typography>Operating CF: ${parseFloat(item.operating_cash_flow || 0).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>
                        <Grid item xs={12} sm={6}><Typography>Investing CF: ${parseFloat(item.investing_cash_flow || 0).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>
                        {item.financing_cash_flow && <Grid item xs={12} sm={6}><Typography>Financing CF: ${parseFloat(item.financing_cash_flow).toLocaleString('en-US', {maximumFractionDigits: 0})}</Typography></Grid>}
                      </Grid>
                    </Box>
                  ))}
                </CardContent>
              </Card>
            ) : (
              <Alert severity="info">No cash flow data available</Alert>
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
                  <Typography variant="h6" sx={{ mb: 2 }}>Key Metrics - {ticker}</Typography>
                  <Grid container spacing={2}>
                    {keyMetricsData.data.pe_ratio && <Grid item xs={12} sm={6}><Typography>P/E Ratio: {keyMetricsData.data.pe_ratio}</Typography></Grid>}
                    {keyMetricsData.data.dividend_yield && <Grid item xs={12} sm={6}><Typography>Dividend Yield: {(parseFloat(keyMetricsData.data.dividend_yield) * 100).toFixed(2)}%</Typography></Grid>}
                    {keyMetricsData.data.debt_to_equity && <Grid item xs={12} sm={6}><Typography>Debt/Equity: {keyMetricsData.data.debt_to_equity}</Typography></Grid>}
                    {keyMetricsData.data.current_ratio && <Grid item xs={12} sm={6}><Typography>Current Ratio: {keyMetricsData.data.current_ratio}</Typography></Grid>}
                  </Grid>
                </CardContent>
              </Card>
            ) : (
              <Alert severity="info">No key metrics data available</Alert>
            )}
          </Box>
        )}
      </Box>
    </Container>
  );
}

export default FinancialData;
