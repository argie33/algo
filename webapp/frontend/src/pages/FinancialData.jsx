import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createComponentLogger } from "../utils/errorLogger";
import {
  Alert,
  Autocomplete,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Divider,
  Grid,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Tabs,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  AccountBalance,
  Analytics,
  Timeline,
  Search,
  ShowChart,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";

// Use centralized error logging (logger will be defined in component)

import {
  getBalanceSheet,
  getIncomeStatement,
  getCashFlowStatement,
  getKeyMetrics,
  getStocks,
} from "../services/api";
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
} from "../utils/formatters";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`financial-tabpanel-${index}`}
      aria-labelledby={`financial-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

function FinancialData() {
  if (import.meta.env && import.meta.env.DEV) console.log("🚀 FinancialData: Component rendering...");

  const logger = createComponentLogger("FinancialData");

  const [ticker, setTicker] = useState("AAPL");
  const [searchTicker, _setSearchTicker] = useState("AAPL");
  const [tabValue, setTabValue] = useState(0);
  const [period, setPeriod] = useState("annual");

  // Get list of companies for dropdown
  const { data: companiesData } = useQuery({
    queryKey: ["companies"],
    queryFn: () => getStocks({ limit: 1000, sortBy: "ticker" }),
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => {
      if (import.meta.env && import.meta.env.DEV) console.log("✅ FinancialData: Companies data loaded:", data);
    },
    onError: (error) =>
      console.error("❌ FinancialData: Companies data error:", error),
  });

  const companies =
    companiesData?.data?.data ?? companiesData?.data ?? companiesData ?? [];
  if (import.meta.env && import.meta.env.DEV) console.log("📊 FinancialData: Companies data:", {
    hasData: !!companiesData,
    companiesLength: (companies?.length || 0),
    sampleCompany: companies[0],
  });

  // Defensive: ensure companies is always an array before using .find
  const safeCompanies = Array.isArray(companies) ? companies : [];

  const handleTabChange = (event, newValue) => {
    if (import.meta.env && import.meta.env.DEV) console.log("🔄 FinancialData: Tab changed to:", newValue);
    setTabValue(newValue);
  };

  const _handleTickerSubmit = () => {
    if (searchTicker.trim()) {
      if (import.meta.env && import.meta.env.DEV) console.log(
        "🔍 FinancialData: Searching for ticker:",
        searchTicker.trim().toUpperCase()
      );
      setTicker(searchTicker.trim().toUpperCase());
    }
  };

  const handlePeriodChange = (event, newPeriod) => {
    if (newPeriod !== null) {
      if (import.meta.env && import.meta.env.DEV) console.log("📅 FinancialData: Period changed to:", newPeriod);
      setPeriod(newPeriod);
    }
  };

  // Comprehensive financial data queries
  const {
    data: balanceSheet,
    isLoading: balanceSheetLoading,
    error: balanceSheetError,
  } = useQuery({
    queryKey: ["balanceSheet", ticker, period],
    queryFn: () => getBalanceSheet(ticker, period),
    enabled: !!ticker && tabValue === 0,
    onSuccess: (data) => {
      if (import.meta.env && import.meta.env.DEV) console.log("✅ FinancialData: Balance sheet loaded:", data);
    },
    onError: (error) => {
      console.error("❌ FinancialData: Balance sheet error:", error);
      logger.queryError("balanceSheet", error, { ticker, period });
    },
  });

  const {
    data: incomeStatement,
    isLoading: incomeStatementLoading,
    error: incomeStatementError,
  } = useQuery({
    queryKey: ["incomeStatement", ticker, period],
    queryFn: () => getIncomeStatement(ticker, period),
    enabled: !!ticker && tabValue === 1,
    onSuccess: (data) => {
      if (import.meta.env && import.meta.env.DEV) console.log("✅ FinancialData: Income statement loaded:", data);
    },
    onError: (error) => {
      console.error("❌ FinancialData: Income statement error:", error);
      logger.queryError("incomeStatement", error, { ticker, period });
    },
  });

  const {
    data: cashFlowStatement,
    isLoading: cashFlowLoading,
    error: cashFlowError,
  } = useQuery({
    queryKey: ["cashFlowStatement", ticker, period],
    queryFn: () => getCashFlowStatement(ticker, period),
    enabled: !!ticker && tabValue === 2,
    onSuccess: (data) => {
      if (import.meta.env && import.meta.env.DEV) console.log("✅ FinancialData: Cash flow statement loaded:", data);
    },
    onError: (error) => {
      console.error("❌ FinancialData: Cash flow statement error:", error);
      logger.queryError("cashFlowStatement", error, { ticker, period });
    },
  });

  if (import.meta.env && import.meta.env.DEV) console.log("📊 FinancialData: Data summary:", {
    ticker,
    period,
    tabValue,
    balanceSheet: {
      hasData: !!balanceSheet,
      isLoading: balanceSheetLoading,
      hasError: !!balanceSheetError,
    },
    incomeStatement: {
      hasData: !!incomeStatement,
      isLoading: incomeStatementLoading,
      hasError: !!incomeStatementError,
    },
    cashFlowStatement: {
      hasData: !!cashFlowStatement,
      isLoading: cashFlowLoading,
      hasError: !!cashFlowError,
    },
  });

  const {
    data: keyMetrics,
    isLoading: keyMetricsLoading,
    error: keyMetricsError,
  } = useQuery({
    queryKey: ["keyMetrics", ticker],
    queryFn: () => getKeyMetrics(ticker),
    enabled: !!ticker && tabValue === 3,
    onError: (error) => logger.queryError("keyMetrics", error, { ticker }),
  });
  const renderKeyMetrics = (data) => {
    // Handle error response
    if (data?.error) {
      return (
        <Card>
          <CardContent>
            <Typography
              variant="h6"
              gutterBottom
              sx={{ display: "flex", alignItems: "center" }}
            >
              <ShowChart />
              <Box sx={{ ml: 1 }}>Key Metrics</Box>
            </Typography>
            <Alert severity="error">
              Error loading key metrics: {data.error}
            </Alert>
          </CardContent>
        </Card>
      );
    }

    // Access data from the { data: {...} } structure returned by API
    const metricsData = data?.data || data;

    if (!metricsData) {
      return (
        <Card>
          <CardContent>
            <Typography
              variant="h6"
              gutterBottom
              sx={{ display: "flex", alignItems: "center" }}
            >
              <ShowChart />
              <Box sx={{ ml: 1 }}>Key Metrics</Box>
            </Typography>
            <Alert severity="info">
              No key metrics data available for {ticker}
            </Alert>
          </CardContent>
        </Card>
      );
    }

    // The API returns organized categories, render each category as a separate card
    return (
      <Box>
        <Typography
          variant="h5"
          gutterBottom
          sx={{ display: "flex", alignItems: "center", mb: 3 }}
        >
          <ShowChart />
          <Box sx={{ ml: 1 }}>Key Metrics - {ticker}</Box>
        </Typography>

        <Grid container spacing={3}>
          {Object.entries(metricsData).map(([categoryKey, category]) => (
            <Grid item xs={12} md={6} lg={4} key={categoryKey}>
              <Card>
                <CardContent>
                  <Typography
                    variant="h6"
                    gutterBottom
                    sx={{ display: "flex", alignItems: "center" }}
                  >
                    {/* We can add icons based on category later */}
                    <Box sx={{ ml: 0 }}>{category.title}</Box>
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                  <TableContainer>
                    <Table size="small">
                      <TableBody>
                        {Object.entries(category.metrics).map(
                          ([metricName, value]) => (
                            <TableRow key={metricName}>
                              <TableCell
                                component="th"
                                scope="row"
                                sx={{ py: 1, fontSize: "0.875rem" }}
                              >
                                {metricName}
                              </TableCell>
                              <TableCell
                                align="right"
                                sx={{
                                  py: 1,
                                  fontSize: "0.875rem",
                                  fontWeight: "medium",
                                }}
                              >
                                {value !== null && value !== undefined
                                  ? typeof value === "number"
                                    ? metricName.includes("%") ||
                                      metricName.includes("Margin") ||
                                      metricName.includes("Growth") ||
                                      metricName.includes("Yield") ||
                                      metricName.includes("Return")
                                      ? formatPercentage(value)
                                      : metricName.includes("$") ||
                                          metricName.includes("Revenue") ||
                                          metricName.includes("Income") ||
                                          metricName.includes("Cash") ||
                                          metricName.includes("Value") ||
                                          metricName.includes("Debt")
                                        ? formatCurrency(value)
                                        : formatNumber(value)
                                    : value
                                  : "N/A"}
                              </TableCell>
                            </TableRow>
                          )
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  };
  const renderFinancialTable = (data, title, icon) => {
    // Handle error response
    if (data?.error) {
      return (
        <Card>
          <CardContent>
            <Typography
              variant="h6"
              gutterBottom
              sx={{ display: "flex", alignItems: "center" }}
            >
              {icon}
              <Box sx={{ ml: 1 }}>{title}</Box>
            </Typography>
            <Alert severity="error">
              Error loading {title.toLowerCase()}: {data.error}
            </Alert>
          </CardContent>
        </Card>
      );
    }

    // Access data from the { data: [...] } structure returned by API
    let actualData = data?.data || data;

    // If the data is wrapped in a 'success' or 'metadata' object, unwrap it
    if (
      actualData &&
      typeof actualData === "object" &&
      !Array.isArray(actualData)
    ) {
      if ("data" in actualData) actualData = actualData?.data;
    }
    if (!actualData || !Array.isArray(actualData) || (actualData?.length || 0) === 0) {
      return (
        <Card>
          <CardContent>
            <Typography
              variant="h6"
              gutterBottom
              sx={{ display: "flex", alignItems: "center" }}
            >
              {icon}
              <Box sx={{ ml: 1 }}>{title}</Box>
            </Typography>
            <Alert severity="info">
              No {title.toLowerCase()} data available for {ticker}
            </Alert>
          </CardContent>
        </Card>
      );
    }

    // Handle the new normalized table structure (symbol, date, item_name, value)
    const isNormalizedStructure =
      actualData.length > 0 && actualData[0].item_name !== undefined;

    if (isNormalizedStructure) {
      // Group by date for the new structure
      const groupedByDate = {};
      actualData.forEach((item) => {
        if (!groupedByDate[item.date]) {
          groupedByDate[item.date] = [];
        }
        groupedByDate[item.date].push(item);
      });

      const periods = Object.entries(groupedByDate).map(([date, items]) => ({
        date,
        items: items.reduce((acc, item) => {
          acc[item.item_name] = item.value;
          return acc;
        }, {}),
      }));

      return (
        <Card>
          <CardContent>
            <Typography
              variant="h6"
              gutterBottom
              sx={{ display: "flex", alignItems: "center" }}
            >
              {icon}
              <Box sx={{ ml: 1 }}>
                {title} - {ticker}
              </Box>
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <Grid container spacing={3}>
              {periods.slice(0, 5).map((period, index) => (
                <Grid item xs={12} md={6} lg={4} key={period.date || index}>
                  <Card variant="outlined">
                    <CardContent sx={{ p: 2 }}>
                      <Typography
                        variant="subtitle1"
                        sx={{ fontWeight: "bold", mb: 2 }}
                      >
                        {period.date
                          ? new Date(period.date).getFullYear()
                          : "N/A"}
                      </Typography>
                      <TableContainer>
                        <Table size="small">
                          <TableBody>
                            {period.items &&
                              Object.entries(period.items)
                                .slice(0, 10)
                                .map(([key, value]) => (
                                  <TableRow key={key}>
                                    <TableCell
                                      sx={{
                                        py: 0.5,
                                        fontSize: "0.875rem",
                                        border: "none",
                                      }}
                                    >
                                      {key.replace(/([A-Z])/g, " $1").trim()}
                                    </TableCell>
                                    <TableCell
                                      align="right"
                                      sx={{
                                        py: 0.5,
                                        fontSize: "0.875rem",
                                        fontWeight: "bold",
                                        border: "none",
                                      }}
                                    >
                                      {value || value === 0
                                        ? formatCurrency(value, 0)
                                        : "N/A"}
                                    </TableCell>
                                  </TableRow>
                                ))}
                            {!period.items && (
                              <TableRow>
                                <TableCell
                                  colSpan={2}
                                  sx={{
                                    py: 1,
                                    fontSize: "0.875rem",
                                    border: "none",
                                    textAlign: "center",
                                    color: "text.secondary",
                                  }}
                                >
                                  No financial data available for this period
                                </TableCell>
                              </TableRow>
                            )}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
            {/* Trend Chart */}
            <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Trend Analysis
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart
                  data={periods
                    .slice(0, 5)
                    .reverse()
                    .map((period) => {
                      const items = period.items;
                      const firstItem =
                        items && Object.keys(items).length > 0
                          ? Object.entries(items)[0]
                          : null;
                      return {
                        year: period.date
                          ? new Date(period.date).getFullYear()
                          : "N/A",
                        value: firstItem ? firstItem[1] : 0,
                        name: firstItem ? firstItem[0] : "N/A",
                      };
                    })}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis />
                  <Tooltip
                    formatter={(value, _name) => [
                      formatCurrency(value, 0),
                      "Value",
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#1976d2"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      );
    }

    // Handle the old structure (periods with items)
    return (
      <Card>
        <CardContent>
          <Typography
            variant="h6"
            gutterBottom
            sx={{ display: "flex", alignItems: "center" }}
          >
            {icon}
            <Box sx={{ ml: 1 }}>
              {title} - {ticker}
            </Box>
          </Typography>
          <Divider sx={{ mb: 2 }} />
          <Grid container spacing={3}>
            {actualData.slice(0, 5).map((period, index) => (
              <Grid item xs={12} md={6} lg={4} key={period.date || index}>
                <Card variant="outlined">
                  <CardContent sx={{ p: 2 }}>
                    <Typography
                      variant="subtitle1"
                      sx={{ fontWeight: "bold", mb: 2 }}
                    >
                      {period.date
                        ? new Date(period.date).getFullYear()
                        : "N/A"}
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableBody>
                          {period.items &&
                            Object.entries(period.items)
                              .slice(0, 10)
                              .map(([key, value]) => (
                                <TableRow key={key}>
                                  <TableCell
                                    sx={{
                                      py: 0.5,
                                      fontSize: "0.875rem",
                                      border: "none",
                                    }}
                                  >
                                    {key.replace(/([A-Z])/g, " $1").trim()}
                                  </TableCell>
                                  <TableCell
                                    align="right"
                                    sx={{
                                      py: 0.5,
                                      fontSize: "0.875rem",
                                      fontWeight: "bold",
                                      border: "none",
                                    }}
                                  >
                                    {value || value === 0
                                      ? formatCurrency(value, 0)
                                      : "N/A"}
                                  </TableCell>
                                </TableRow>
                              ))}
                          {!period.items && (
                            <TableRow>
                              <TableCell
                                colSpan={2}
                                sx={{
                                  py: 1,
                                  fontSize: "0.875rem",
                                  border: "none",
                                  textAlign: "center",
                                  color: "text.secondary",
                                }}
                              >
                                No financial data available for this period
                              </TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
          {/* Trend Chart */}
          <Box sx={{ mt: 4 }}>
            <Typography variant="h6" gutterBottom>
              Trend Analysis
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart
                data={actualData
                  .slice(0, 5)
                  .reverse()
                  .map((period) => {
                    const items = period.items;
                    const firstItem =
                      items && Object.keys(items).length > 0
                        ? Object.entries(items)[0]
                        : null;
                    return {
                      year: period.date
                        ? new Date(period.date).getFullYear()
                        : "N/A",
                      value: firstItem ? firstItem[1] : 0,
                      name: firstItem ? firstItem[0] : "N/A",
                    };
                  })}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis />
                <Tooltip
                  formatter={(value, _name) => [
                    formatCurrency(value, 0),
                    "Value",
                  ]}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#1976d2"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </Box>
        </CardContent>
      </Card>
    );
  };

  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 3 }}>
        {/* Enhanced Header */}
        <Box sx={{ mb: 4 }}>
          <Typography
            variant="h3"
            component="h1"
            gutterBottom
            sx={{ fontWeight: 700, color: "primary.main" }}
          >
            📊 Financial Data Analysis
          </Typography>
          <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 3 }}>
            Comprehensive financial statements, earnings data, and
            institutional-grade fundamental analysis
          </Typography>
        </Box>
        {/* Search Section */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} md={4}>
                <Autocomplete
                  options={safeCompanies}
                  getOptionLabel={(option) =>
                    `${option.ticker} - ${option.short_name || option.ticker}`
                  }
                  value={safeCompanies.find((c) => c.ticker === ticker) || null}
                  onChange={(event, newValue) => {
                    if (newValue) {
                      setTicker(newValue.ticker);
                    }
                  }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Select Company"
                      placeholder="Search companies..."
                      InputProps={{
                        ...params.InputProps,
                        startAdornment: (
                          <Search sx={{ mr: 1, color: "text.secondary" }} />
                        ),
                      }}
                    />
                  )}
                  renderOption={(props, option) => (
                    <Box component="li" {...props}>
                      <Box>
                        <Typography variant="body2" sx={{ fontWeight: "bold" }}>
                          {option.ticker}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {option.short_name}
                        </Typography>
                      </Box>
                    </Box>
                  )}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <ToggleButtonGroup
                  value={period}
                  exclusive
                  onChange={handlePeriodChange}
                  size="small"
                >
                  <ToggleButton value="annual">Annual</ToggleButton>
                  <ToggleButton value="quarterly">Quarterly</ToggleButton>
                  <ToggleButton value="ttm">TTM</ToggleButton>{" "}
                </ToggleButtonGroup>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
        {/* Tabs */}{" "}
        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
          <Tabs value={tabValue} onChange={handleTabChange}>
            <Tab value={0} label="Balance Sheet" icon={<AccountBalance />} />
            <Tab value={1} label="Income Statement" icon={<Analytics />} />
            <Tab value={2} label="Cash Flow" icon={<Timeline />} />
            <Tab value={3} label="Key Metrics" icon={<ShowChart />} />
          </Tabs>
        </Box>
        {/* Tab Panels */}
        <TabPanel value={tabValue} index={0}>
          {balanceSheetLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : balanceSheetError ? (
            <Alert severity="error">
              Failed to load balance sheet: {balanceSheetError.message}
            </Alert>
          ) : (
            renderFinancialTable(
              balanceSheet,
              "Balance Sheet",
              <AccountBalance />
            )
          )}
        </TabPanel>
        <TabPanel value={tabValue} index={1}>
          {incomeStatementLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : incomeStatementError ? (
            <Alert severity="error">
              Failed to load income statement: {incomeStatementError.message}
            </Alert>
          ) : (
            renderFinancialTable(
              incomeStatement,
              "Income Statement",
              <Analytics />
            )
          )}
        </TabPanel>
        <TabPanel value={tabValue} index={2}>
          {cashFlowLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : cashFlowError ? (
            <Alert severity="error">
              Failed to load cash flow: {cashFlowError.message}
            </Alert>
          ) : (
            renderFinancialTable(
              cashFlowStatement,
              "Cash Flow Statement",
              <Timeline />
            )
          )}
        </TabPanel>
        <TabPanel value={tabValue} index={3}>
          {keyMetricsLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : keyMetricsError ? (
            <Alert severity="error">
              Failed to load key metrics: {keyMetricsError.message}
            </Alert>
          ) : (
            renderKeyMetrics(keyMetrics)
          )}
        </TabPanel>
      </Box>
    </Container>
  );
}

export default FinancialData;
