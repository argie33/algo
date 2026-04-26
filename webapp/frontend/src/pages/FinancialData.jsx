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
            ) : balanceSheetData ? (
              <Alert severity="success">Balance Sheet loaded</Alert>
            ) : (
              <Alert severity="info">Select a company to view data</Alert>
            )}
          </Box>
        )}

        {tabValue === 1 && (
          <Box>
            {isLoading ? (
              <CircularProgress />
            ) : incomeStatementData ? (
              <Alert severity="success">Income Statement loaded</Alert>
            ) : (
              <Alert severity="info">Select a company to view data</Alert>
            )}
          </Box>
        )}

        {tabValue === 2 && (
          <Box>
            {cfLoading ? (
              <CircularProgress />
            ) : cashFlowData ? (
              <Alert severity="success">Cash Flow loaded</Alert>
            ) : (
              <Alert severity="info">Select a company to view data</Alert>
            )}
          </Box>
        )}

        {tabValue === 3 && (
          <Box>
            {kmLoading ? (
              <CircularProgress />
            ) : keyMetricsData ? (
              <Alert severity="success">Key Metrics loaded</Alert>
            ) : (
              <Alert severity="info">Select a company to view data</Alert>
            )}
          </Box>
        )}
      </Box>
    </Container>
  );
}

export default FinancialData;
