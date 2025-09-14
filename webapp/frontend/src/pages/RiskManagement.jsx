import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import {
  Security,
  Warning,
  Assessment,
  Timeline,
  Shield,
  Error as ErrorIcon,
  CheckCircle,
  Notifications,
  Speed,
  Refresh,
  InfoOutlined,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
} from "recharts";
import {
  getRiskAnalysis,
  getRiskAlerts,
  createRiskAlert,
  getRiskDashboard,
} from "../services/api";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`risk-tabpanel-${index}`}
      aria-labelledby={`risk-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const RiskManagement = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [selectedPeriod, setSelectedPeriod] = useState("1m");
  const [confidenceLevel, setConfidenceLevel] = useState(0.95);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [newAlert, setNewAlert] = useState({
    symbol: "",
    metric: "volatility",
    threshold: 25,
    condition: "above",
  });

  // Queries for real API data
  const {
    data: riskDashboard,
    isLoading: isDashboardLoading,
    error: dashboardError,
    refetch: refetchDashboard,
  } = useQuery({
    queryKey: ["risk-dashboard", selectedPeriod],
    queryFn: () => getRiskDashboard({ period: selectedPeriod }),
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 2,
  });

  const {
    data: riskAnalysis,
    isLoading: isAnalysisLoading,
    error: analysisError,
  } = useQuery({
    queryKey: ["risk-analysis", selectedPeriod, confidenceLevel],
    queryFn: () =>
      getRiskAnalysis({
        period: selectedPeriod,
        confidence_level: confidenceLevel,
      }),
    staleTime: 5 * 60 * 1000,
    retry: 2,
  });

  const {
    data: riskAlerts,
    isLoading: isAlertsLoading,
    error: alertsError,
    refetch: refetchAlerts,
  } = useQuery({
    queryKey: ["risk-alerts"],
    queryFn: getRiskAlerts,
    staleTime: 2 * 60 * 1000, // 2 minutes for alerts
    retry: 2,
  });

  const isLoading = isDashboardLoading || isAnalysisLoading || isAlertsLoading;
  const hasError = dashboardError || analysisError || alertsError;

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handlePeriodChange = (event) => {
    setSelectedPeriod(event.target.value);
  };

  const handleConfidenceLevelChange = (event) => {
    setConfidenceLevel(parseFloat(event.target.value));
  };

  const getRiskColor = (value, thresholds) => {
    if (value <= thresholds.low) return "success";
    if (value <= thresholds.medium) return "warning";
    return "error";
  };

  const getSeverityIcon = (severity) => {
    switch (severity?.toLowerCase()) {
      case "high":
      case "critical":
        return <ErrorIcon color="error" />;
      case "medium":
      case "warning":
        return <Warning color="warning" />;
      case "low":
      case "info":
        return <CheckCircle color="success" />;
      default:
        return <InfoOutlined color="info" />;
    }
  };

  const handleCreateAlert = async () => {
    try {
      await createRiskAlert(newAlert);
      setAlertDialogOpen(false);
      refetchAlerts();
      // Reset form
      setNewAlert({
        symbol: "",
        metric: "volatility",
        threshold: 25,
        condition: "above",
      });
    } catch (error) {
      console.error("Error creating risk alert:", error);
    }
  };

  const formatCurrency = (value) => {
    if (!value) return "N/A";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatPercentage = (value, decimals = 2) => {
    if (value === null || value === undefined) return "N/A";
    return `${(value * 100).toFixed(decimals)}%`;
  };

  if (isLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="60vh"
        >
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  if (hasError) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Alert severity="error" sx={{ mb: 3 }}>
          <Typography variant="subtitle1">
            Failed to load risk management data
          </Typography>
          <Typography variant="body2">
            {dashboardError?.message ||
              analysisError?.message ||
              alertsError?.message}
          </Typography>
        </Alert>
      </Container>
    );
  }

  const portfolioMetrics = riskDashboard?.portfolio_metrics || {};
  const positionRisks = riskAnalysis?.position_risks || [];
  const alerts = riskAlerts?.data || [];

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* Header with Controls */}
      <Box
        sx={{
          mb: 3,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <Box>
          <Typography
            variant="h4"
            gutterBottom
            sx={{ fontWeight: 700, display: "flex", alignItems: "center" }}
          >
            <Security sx={{ mr: 2, color: "primary.main" }} />
            Risk Management
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Comprehensive portfolio risk analysis, monitoring, and stress
            testing with real-time alerts.
          </Typography>
        </Box>

        <Box sx={{ display: "flex", gap: 2 }}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Period</InputLabel>
            <Select
              value={selectedPeriod}
              label="Period"
              onChange={handlePeriodChange}
            >
              <MenuItem value="1d">1 Day</MenuItem>
              <MenuItem value="1w">1 Week</MenuItem>
              <MenuItem value="1m">1 Month</MenuItem>
              <MenuItem value="3m">3 Months</MenuItem>
              <MenuItem value="6m">6 Months</MenuItem>
              <MenuItem value="1y">1 Year</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Confidence</InputLabel>
            <Select
              value={confidenceLevel}
              label="Confidence"
              onChange={handleConfidenceLevelChange}
            >
              <MenuItem value={0.9}>90%</MenuItem>
              <MenuItem value={0.95}>95%</MenuItem>
              <MenuItem value={0.99}>99%</MenuItem>
            </Select>
          </FormControl>

          <IconButton onClick={refetchDashboard} color="primary" size="large">
            <Refresh />
          </IconButton>
        </Box>
      </Box>

      {/* Risk Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Box>
                  <Typography color="text.secondary" gutterBottom>
                    Portfolio VaR ({(confidenceLevel * 100).toFixed(0)}%)
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {formatCurrency(
                      portfolioMetrics.var_95 || portfolioMetrics.var
                    )}
                  </Typography>
                </Box>
                <Shield sx={{ fontSize: 40, color: "primary.main" }} />
              </Box>
              <LinearProgress
                variant="determinate"
                value={Math.min(
                  ((portfolioMetrics.var_95 || 0) /
                    (portfolioMetrics.total_value || 1)) *
                    100,
                  100
                )}
                sx={{ mt: 1 }}
                color={getRiskColor(
                  ((portfolioMetrics.var_95 || 0) /
                    (portfolioMetrics.total_value || 1)) *
                    100,
                  { low: 3, medium: 8 }
                )}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Box>
                  <Typography color="text.secondary" gutterBottom>
                    Sharpe Ratio
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {portfolioMetrics.sharpe_ratio?.toFixed(2) || "N/A"}
                  </Typography>
                </Box>
                <Assessment sx={{ fontSize: 40, color: "success.main" }} />
              </Box>
              <Chip
                label={
                  (portfolioMetrics.sharpe_ratio || 0) > 1
                    ? "Good"
                    : "Needs Improvement"
                }
                color={
                  (portfolioMetrics.sharpe_ratio || 0) > 1
                    ? "success"
                    : "warning"
                }
                size="small"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Box>
                  <Typography color="text.secondary" gutterBottom>
                    Portfolio Beta
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {portfolioMetrics.beta?.toFixed(2) || "N/A"}
                  </Typography>
                </Box>
                <Timeline sx={{ fontSize: 40, color: "warning.main" }} />
              </Box>
              <Chip
                label={
                  Math.abs((portfolioMetrics.beta || 1) - 1) < 0.2
                    ? "Market Neutral"
                    : "Market Sensitive"
                }
                color={
                  Math.abs((portfolioMetrics.beta || 1) - 1) < 0.2
                    ? "success"
                    : "warning"
                }
                size="small"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Box>
                  <Typography color="text.secondary" gutterBottom>
                    Volatility
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {formatPercentage(portfolioMetrics.volatility, 1)}
                  </Typography>
                </Box>
                <Speed sx={{ fontSize: 40, color: "error.main" }} />
              </Box>
              <LinearProgress
                variant="determinate"
                value={Math.min((portfolioMetrics.volatility || 0) * 100, 100)}
                sx={{ mt: 1 }}
                color={getRiskColor((portfolioMetrics.volatility || 0) * 100, {
                  low: 15,
                  medium: 25,
                })}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs for detailed risk analysis */}
      <Card>
        <CardHeader
          title={
            <Tabs value={activeTab} onChange={handleTabChange}>
              <Tab label="Position Risk" />
              <Tab label="VaR Analysis" />
              <Tab label="Stress Testing" />
              <Tab label="Risk Alerts" />
            </Tabs>
          }
        />

        <TabPanel value={activeTab} index={0}>
          <Typography variant="h6" gutterBottom>
            Position Risk Analysis
          </Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell align="right">Weight</TableCell>
                  <TableCell align="right">
                    VaR ({(confidenceLevel * 100).toFixed(0)}%)
                  </TableCell>
                  <TableCell align="right">Beta</TableCell>
                  <TableCell align="right">Volatility</TableCell>
                  <TableCell align="right">Risk Contribution</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {positionRisks.map((position) => (
                  <TableRow key={position.symbol}>
                    <TableCell>
                      <Box sx={{ display: "flex", alignItems: "center" }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {position.symbol}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      {formatPercentage(position.weight, 1)}
                    </TableCell>
                    <TableCell align="right">
                      {formatCurrency(position.var)}
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={position.beta?.toFixed(2) || "N/A"}
                        color={getRiskColor(position.beta || 1, {
                          low: 0.8,
                          medium: 1.2,
                        })}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={formatPercentage(position.volatility, 1)}
                        color={getRiskColor((position.volatility || 0) * 100, {
                          low: 20,
                          medium: 30,
                        })}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">
                      <LinearProgress
                        variant="determinate"
                        value={(position.risk_contribution || 0) * 100}
                        sx={{ width: 60 }}
                        color={getRiskColor(
                          (position.risk_contribution || 0) * 100,
                          {
                            low: 20,
                            medium: 30,
                          }
                        )}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </TabPanel>

        <TabPanel value={activeTab} index={1}>
          <Typography variant="h6" gutterBottom>
            Value at Risk Analysis
          </Typography>
          {riskAnalysis?.historical_var && (
            <Box sx={{ height: 400, mt: 2 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={riskAnalysis.historical_var}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <ChartTooltip
                    formatter={(value) => [`$${value.toLocaleString()}`, ""]}
                  />
                  <Line
                    type="monotone"
                    dataKey="var_95"
                    stroke="#1976d2"
                    name="VaR 95%"
                    strokeWidth={2}
                  />
                  <Line
                    type="monotone"
                    dataKey="var_99"
                    stroke="#d32f2f"
                    name="VaR 99%"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          )}
        </TabPanel>

        <TabPanel value={activeTab} index={2}>
          <Typography variant="h6" gutterBottom>
            Stress Test Results
          </Typography>
          {riskAnalysis?.stress_tests && (
            <Grid container spacing={2}>
              {riskAnalysis.stress_tests.map((test, index) => (
                <Grid item xs={12} md={6} key={index}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                        {test.scenario}
                      </Typography>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                          mt: 1,
                        }}
                      >
                        <Typography color="text.secondary">
                          Potential Loss:
                        </Typography>
                        <Typography
                          sx={{ color: "error.main", fontWeight: 600 }}
                        >
                          {formatCurrency(Math.abs(test.loss))} (
                          {Math.abs(test.percentage).toFixed(1)}%)
                        </Typography>
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={Math.abs(test.percentage)}
                        color="error"
                        sx={{ mt: 1 }}
                      />
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={activeTab} index={3}>
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              mb: 2,
            }}
          >
            <Typography variant="h6">Risk Alerts</Typography>
            <Button
              variant="contained"
              startIcon={<Notifications />}
              onClick={() => setAlertDialogOpen(true)}
            >
              Create Alert
            </Button>
          </Box>

          {alerts.map((alert) => (
            <Alert
              key={alert.id}
              severity={alert.severity?.toLowerCase() || "info"}
              icon={getSeverityIcon(alert.severity)}
              sx={{ mb: 2 }}
            >
              <Typography variant="body2">
                <strong>{alert.symbol}</strong> {alert.metric} is {alert.value}
                {typeof alert.value === "number" && alert.value < 10 ? "" : "%"}
                (threshold: {alert.threshold}
                {typeof alert.threshold === "number" && alert.threshold < 10
                  ? ""
                  : "%"}
                )
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {new Date(alert.timestamp).toLocaleString()}
              </Typography>
            </Alert>
          ))}
        </TabPanel>
      </Card>

      {/* Create Alert Dialog */}
      <Dialog
        open={alertDialogOpen}
        onClose={() => setAlertDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create Risk Alert</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Symbol"
                value={newAlert.symbol}
                onChange={(e) =>
                  setNewAlert({ ...newAlert, symbol: e.target.value })
                }
                placeholder="e.g., AAPL or PORTFOLIO"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Metric</InputLabel>
                <Select
                  value={newAlert.metric}
                  onChange={(e) =>
                    setNewAlert({ ...newAlert, metric: e.target.value })
                  }
                >
                  <MenuItem value="volatility">Volatility</MenuItem>
                  <MenuItem value="beta">Beta</MenuItem>
                  <MenuItem value="var">Value at Risk</MenuItem>
                  <MenuItem value="concentration">Concentration</MenuItem>
                  <MenuItem value="correlation">Correlation</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>Condition</InputLabel>
                <Select
                  value={newAlert.condition}
                  onChange={(e) =>
                    setNewAlert({ ...newAlert, condition: e.target.value })
                  }
                >
                  <MenuItem value="above">Above</MenuItem>
                  <MenuItem value="below">Below</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="Threshold"
                type="number"
                value={newAlert.threshold}
                onChange={(e) =>
                  setNewAlert({
                    ...newAlert,
                    threshold: Number(e.target.value),
                  })
                }
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAlertDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleCreateAlert} variant="contained">
            Create Alert
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default RiskManagement;
