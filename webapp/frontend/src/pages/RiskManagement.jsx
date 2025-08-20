import React, { useState, useEffect } from "react";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  LinearProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tooltip,
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
  Speed
} from "@mui/icons-material";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer } from "recharts";
import { getApiConfig } from "../services/api";

const { apiUrl: API_BASE } = getApiConfig();

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
  const [loading, setLoading] = useState(false);
  const [riskData, setRiskData] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState("AAPL");
  const [portfolioRisk, setPortfolioRisk] = useState(null);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [newAlert, setNewAlert] = useState({
    symbol: "",
    metric: "volatility",
    threshold: 25,
    condition: "above",
  });

  // ⚠️ MOCK DATA - Replace with real API when available
  const mockRiskData = {
    isMockData: true,
    portfolioMetrics: {
      totalValue: 1250000,
      var95: 68500,
      var99: 125000,
      sharpeRatio: 1.42,
      beta: 1.15,
      volatility: 0.18,
      maxDrawdown: 0.125,
      correlation: 0.89,
      concentrationRisk: 0.35,
    },
    positionRisks: [
      {
        symbol: "AAPL",
        weight: 0.25,
        var: 15000,
        beta: 1.12,
        volatility: 0.22,
        contribution: 0.28,
      },
      {
        symbol: "MSFT",
        weight: 0.2,
        var: 12000,
        beta: 0.98,
        volatility: 0.19,
        contribution: 0.22,
      },
      {
        symbol: "GOOGL",
        weight: 0.18,
        var: 11000,
        beta: 1.25,
        volatility: 0.24,
        contribution: 0.25,
      },
      {
        symbol: "TSLA",
        weight: 0.15,
        var: 22000,
        beta: 1.8,
        volatility: 0.35,
        contribution: 0.35,
      },
      {
        symbol: "NVDA",
        weight: 0.12,
        var: 18000,
        beta: 1.65,
        volatility: 0.32,
        contribution: 0.28,
      },
    ],
    riskAlerts: [
      {
        id: 1,
        symbol: "TSLA",
        metric: "Volatility",
        value: 35.2,
        threshold: 30,
        severity: "high",
        timestamp: "2025-07-03T10:30:00Z",
      },
      {
        id: 2,
        symbol: "PORTFOLIO",
        metric: "Concentration",
        value: 35,
        threshold: 30,
        severity: "medium",
        timestamp: "2025-07-03T09:15:00Z",
      },
      {
        id: 3,
        symbol: "NVDA",
        metric: "Beta",
        value: 1.65,
        threshold: 1.5,
        severity: "medium",
        timestamp: "2025-07-03T08:45:00Z",
      },
    ],
    historicalVaR: [
      { date: "2025-06-28", var95: 65000, var99: 120000 },
      { date: "2025-06-29", var95: 67000, var99: 122000 },
      { date: "2025-06-30", var95: 66500, var99: 121000 },
      { date: "2025-07-01", var95: 68000, var99: 124000 },
      { date: "2025-07-02", var95: 68500, var99: 125000 },
    ],
    stressTests: [
      { scenario: "2008 Financial Crisis", loss: -245000, percentage: -19.6 },
      {
        scenario: "COVID-19 Crash (Mar 2020)",
        loss: -187500,
        percentage: -15.0,
      },
      {
        scenario: "Tech Bubble Burst (2000)",
        loss: -312500,
        percentage: -25.0,
      },
      { scenario: "Flash Crash (May 2010)", loss: -125000, percentage: -10.0 },
    ],
  };

  useEffect(() => {
    loadRiskData();
  }, [selectedSymbol]);

  const loadRiskData = () => {
    setLoading(true);
    try {
      // ⚠️ MOCK DATA - TODO: Replace with real API call
      setTimeout(() => {
        // ⚠️ MOCK DATA - Using mock risk data
        setRiskData(mockRiskData);
        setLoading(false);
      }, 1000);
    } catch (error) {
      console.error("Error loading risk data:", error);
      setLoading(false);
    }
  };

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const getRiskColor = (value, thresholds) => {
    if (value <= thresholds.low) return "success";
    if (value <= thresholds.medium) return "warning";
    return "error";
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case "high":
        return <ErrorIcon color="error" />;
      case "medium":
        return <Warning color="warning" />;
      case "low":
        return <CheckCircle color="success" />;
      default:
        return <CheckCircle color="success" />;
    }
  };

  const handleCreateAlert = () => {
    console.log("Creating risk alert:", newAlert);
    setAlertDialogOpen(false);
    // Reset form
    setNewAlert({
      symbol: "",
      metric: "volatility",
      threshold: 25,
      condition: "above",
    });
  };

  if (loading) {
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

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography
          variant="h4"
          gutterBottom
          sx={{ fontWeight: 700, display: "flex", alignItems: "center" }}
        >
          <Security sx={{ mr: 2, color: "primary.main" }} />
          Risk Management
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Comprehensive portfolio risk analysis, monitoring, and stress testing
          with real-time alerts.
        </Typography>
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
                    Portfolio VaR (95%)
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    ${riskData?.portfolioMetrics.var95.toLocaleString()}
                  </Typography>
                </Box>
                <Shield sx={{ fontSize: 40, color: "primary.main" }} />
              </Box>
              <LinearProgress
                variant="determinate"
                value={
                  (riskData?.portfolioMetrics.var95 /
                    riskData?.portfolioMetrics.totalValue) *
                  100
                }
                sx={{ mt: 1 }}
                color={getRiskColor(
                  (riskData?.portfolioMetrics.var95 /
                    riskData?.portfolioMetrics.totalValue) *
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
                    {riskData?.portfolioMetrics.sharpeRatio}
                  </Typography>
                </Box>
                <Assessment sx={{ fontSize: 40, color: "success.main" }} />
              </Box>
              <Chip
                label={
                  riskData?.portfolioMetrics.sharpeRatio > 1
                    ? "Good"
                    : "Needs Improvement"
                }
                color={
                  riskData?.portfolioMetrics.sharpeRatio > 1
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
                    {riskData?.portfolioMetrics.beta}
                  </Typography>
                </Box>
                <Timeline sx={{ fontSize: 40, color: "warning.main" }} />
              </Box>
              <Chip
                label={
                  Math.abs(riskData?.portfolioMetrics.beta - 1) < 0.2
                    ? "Market Neutral"
                    : "Market Sensitive"
                }
                color={
                  Math.abs(riskData?.portfolioMetrics.beta - 1) < 0.2
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
                    Max Drawdown
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    {(riskData?.portfolioMetrics.maxDrawdown * 100).toFixed(1)}%
                  </Typography>
                </Box>
                <Speed sx={{ fontSize: 40, color: "error.main" }} />
              </Box>
              <LinearProgress
                variant="determinate"
                value={riskData?.portfolioMetrics.maxDrawdown * 100}
                sx={{ mt: 1 }}
                color={getRiskColor(
                  riskData?.portfolioMetrics.maxDrawdown * 100,
                  { low: 10, medium: 20 }
                )}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs for detailed risk analysis */}
      <Card>
        <CardHeader>
          <Tabs value={activeTab} onChange={handleTabChange}>
            <Tab label="Position Risk" />
            <Tab label="VaR Analysis" />
            <Tab label="Stress Testing" />
            <Tab label="Risk Alerts" />
          </Tabs>
        </CardHeader>

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
                  <TableCell align="right">VaR (95%)</TableCell>
                  <TableCell align="right">Beta</TableCell>
                  <TableCell align="right">Volatility</TableCell>
                  <TableCell align="right">Risk Contribution</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {riskData?.positionRisks.map((position) => (
                  <TableRow key={position.symbol}>
                    <TableCell>
                      <Box sx={{ display: "flex", alignItems: "center" }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {position.symbol}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      {(position.weight * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell align="right">
                      ${position.var.toLocaleString()}
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={position.beta.toFixed(2)}
                        color={getRiskColor(position.beta, {
                          low: 0.8,
                          medium: 1.2,
                        })}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={`${(position.volatility * 100).toFixed(1)}%`}
                        color={getRiskColor(position.volatility * 100, {
                          low: 20,
                          medium: 30,
                        })}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">
                      <LinearProgress
                        variant="determinate"
                        value={position.contribution * 100}
                        sx={{ width: 60 }}
                        color={getRiskColor(position.contribution * 100, {
                          low: 20,
                          medium: 30,
                        })}
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
            Value at Risk Trends
          </Typography>
          <Box sx={{ height: 400, mt: 2 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={riskData?.historicalVaR}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip
                  formatter={(value) => [`$${value.toLocaleString()}`, ""]}
                />
                <Line
                  type="monotone"
                  dataKey="var95"
                  stroke="#1976d2"
                  name="VaR 95%"
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="var99"
                  stroke="#d32f2f"
                  name="VaR 99%"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </Box>
        </TabPanel>

        <TabPanel value={activeTab} index={2}>
          <Typography variant="h6" gutterBottom>
            Stress Test Results
          </Typography>
          <Grid container spacing={2}>
            {riskData?.stressTests.map((test, index) => (
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
                      <Typography sx={{ color: "error.main", fontWeight: 600 }}>
                        ${Math.abs(test.loss).toLocaleString()} (
                        {Math.abs(test.percentage)}%)
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

          {riskData?.riskAlerts.map((alert) => (
            <Alert
              key={alert.id}
              severity={alert.severity}
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
