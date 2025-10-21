import { useState, useEffect } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Container,
  Divider,
  Grid,
  IconButton,
  LinearProgress,
  Tab,
  Tabs,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  ShowChart,
  Refresh,
  TrendingFlat,
  Flag,
} from "@mui/icons-material";
import { api } from "../services/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`economic-tabpanel-${index}`}
      aria-labelledby={`economic-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

// Safe formatting helpers
const formatPercent = (value, fallback = "N/A") => {
  if (value === null || value === undefined || isNaN(value)) return fallback;
  return Number(value).toFixed(1);
};

const formatBasisPoints = (value, fallback = "N/A") => {
  if (value === null || value === undefined || isNaN(value)) return fallback;
  return Math.round(Number(value));
};

const getRiskColor = (riskLevel) => {
  if (!riskLevel) return "default";
  switch (riskLevel.toLowerCase()) {
    case "high":
      return "error";
    case "medium":
      return "warning";
    case "low":
      return "success";
    default:
      return "default";
  }
};

const EconomicModeling = () => {
  const [tabValue, setTabValue] = useState(0);
  const [economicData, setEconomicData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Fetch all economic data from backend
  const fetchEconomicData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Use Promise.allSettled to handle partial failures gracefully
      const results = await Promise.allSettled([
        api.get("/api/market/recession-forecast"),
        api.get("/api/market/leading-indicators"),
        api.get("/api/market/sectoral-analysis"),
        api.get("/api/market/economic-scenarios"),
        api.get("/api/market/credit-spreads"),
      ]);

      // Extract successful responses
      const [
        recessionForecast,
        leadingIndicators,
        sectoralAnalysis,
        economicScenarios,
        creditSpreads,
      ] = results.map((result) => (result.status === "fulfilled" ? result.value : null));

      // Check for missing data errors (503 responses)
      const missingDataErrors = results
        .filter((r) => r.status === "fulfilled" && r.value?.status === 503)
        .map((r) => r.value?.data?.missing || [])
        .flat();

      if (missingDataErrors.length > 0 || results.some((r) => r.status === "rejected")) {
        console.warn("⚠️ Some economic data endpoints unavailable:", {
          missing: missingDataErrors,
          rejected: results.filter((r) => r.status === "rejected").length,
        });

        const errorMsg =
          missingDataErrors.length > 0
            ? `Missing economic data: ${missingDataErrors.join(", ")}. Please run loadecondata.py to load FRED data.`
            : "Some economic data endpoints are unavailable. Please try again later.";

        setError(errorMsg);
        setEconomicData(null);
        setLoading(false);
        setRefreshing(false);
        return;
      }

      // Extract data from API responses
      const leadingData = leadingIndicators?.data?.data || {};
      const recessionData = recessionForecast?.data?.data || {};
      const creditData = creditSpreads?.data?.data || {};
      const scenariosData = economicScenarios?.data?.data || {};

      console.log("✅ Economic data loaded:", {
        recession: recessionData.compositeRecessionProbability,
        indicators: leadingData.indicators?.length,
        creditStress: creditData.creditStressIndex,
        events: leadingData.upcomingEvents?.length,
      });

      const combinedData = {
        // Recession data
        recessionProbability: recessionData.compositeRecessionProbability || 0,
        riskLevel: recessionData.riskLevel || "Medium",
        riskIndicator: recessionData.riskIndicator || "🟢",
        economicStressIndex: recessionData.economicStressIndex || 0,
        forecastModels: recessionData.forecastModels || [],
        recessionAnalysis: recessionData.analysis || {},
        keyRecessionIndicators: recessionData.keyIndicators || {},

        // Leading indicators
        leadingIndicators: leadingData.indicators || [],
        gdpGrowth: leadingData.gdpGrowth || 0,
        unemployment: leadingData.unemployment || 0,
        inflation: leadingData.inflation || 0,
        employment: leadingData.employment || {},

        // Yield curve
        yieldCurve: leadingData.yieldCurve || {},
        yieldCurveData: leadingData.yieldCurveData || [],

        // Credit spreads
        creditSpreads: creditData.spreads || {},
        creditStressIndex: creditData.creditStressIndex || 0,
        financialConditionsIndex: creditData.financialConditionsIndex || {},

        // Scenarios
        scenarios: scenariosData.scenarios || [],

        // Calendar
        upcomingEvents: leadingData.upcomingEvents || [],
      };

      setEconomicData(combinedData);
    } catch (err) {
      console.error("Failed to fetch economic data:", err);
      setError(err.message || "Failed to load economic data. Please try again.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchEconomicData();
  }, []);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchEconomicData();
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            🌍 Economic Indicators Dashboard
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Real-time recession probability, credit spreads, and economic health analysis
          </Typography>
        </Box>
        <IconButton onClick={handleRefresh} disabled={refreshing}>
          <Refresh sx={{ animation: refreshing ? "spin 1s linear infinite" : "none" }} />
        </IconButton>
      </Box>

      {/* Loading State */}
      {loading && (
        <Box sx={{ mb: 3 }}>
          <LinearProgress />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1, textAlign: "center" }}>
            Loading economic data...
          </Typography>
        </Box>
      )}

      {/* Error State */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <strong>Error:</strong> {error}
          <Button color="inherit" size="small" onClick={handleRefresh} sx={{ ml: 2 }}>
            Retry
          </Button>
        </Alert>
      )}

      {/* Critical Alert if recession probability high */}
      {!loading && economicData && economicData.recessionProbability > 40 && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          <strong>⚠️ Elevated Recession Risk:</strong> {economicData.recessionProbability}%
          probability. Multiple economic warning signals detected. Monitor market conditions closely.
        </Alert>
      )}

      {/* Key Metrics Summary */}
      {!loading && economicData && (
        <>
          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Recession Probability
                  </Typography>
                  <Typography
                    variant="h3"
                    sx={{
                      color:
                        economicData.recessionProbability > 60
                          ? "error.main"
                          : economicData.recessionProbability > 35
                            ? "warning.main"
                            : "success.main",
                    }}
                  >
                    {economicData.recessionProbability}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={economicData.recessionProbability}
                    color={
                      economicData.recessionProbability > 60
                        ? "error"
                        : economicData.recessionProbability > 35
                          ? "warning"
                          : "success"
                    }
                    sx={{ mt: 2 }}
                  />
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Economic Stress Index
                  </Typography>
                  <Typography
                    variant="h3"
                    sx={{
                      color:
                        economicData.economicStressIndex > 60
                          ? "error.main"
                          : economicData.economicStressIndex > 30
                            ? "warning.main"
                            : "success.main",
                    }}
                  >
                    {economicData.economicStressIndex}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={economicData.economicStressIndex}
                    color={
                      economicData.economicStressIndex > 60
                        ? "error"
                        : economicData.economicStressIndex > 30
                          ? "warning"
                          : "success"
                    }
                    sx={{ mt: 2 }}
                  />
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Credit Stress Index
                  </Typography>
                  <Typography
                    variant="h3"
                    sx={{
                      color:
                        economicData.creditStressIndex > 50
                          ? "error.main"
                          : economicData.creditStressIndex > 30
                            ? "warning.main"
                            : "success.main",
                    }}
                  >
                    {economicData.creditStressIndex}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={economicData.creditStressIndex}
                    color={
                      economicData.creditStressIndex > 50
                        ? "error"
                        : economicData.creditStressIndex > 30
                          ? "warning"
                          : "success"
                    }
                    sx={{ mt: 2 }}
                  />
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" justifyContent="space-between">
                    <Box>
                      <Typography variant="subtitle2" color="text.secondary">
                        Unemployment
                      </Typography>
                      <Typography variant="h4">
                        {formatPercent(economicData.unemployment)}%
                      </Typography>
                    </Box>
                    {economicData.unemployment < 4.5 ? (
                      <TrendingUp color="success" sx={{ fontSize: 40 }} />
                    ) : economicData.unemployment > 5 ? (
                      <TrendingDown color="error" sx={{ fontSize: 40 }} />
                    ) : (
                      <TrendingFlat color="warning" sx={{ fontSize: 40 }} />
                    )}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Tabs */}
          <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
            <Tabs
              value={tabValue}
              onChange={handleTabChange}
              variant="scrollable"
              scrollButtons="auto"
            >
              <Tab value={0} label="Recession Model" icon={<Assessment />} />
              <Tab value={1} label="Leading Indicators" icon={<Analytics />} />
              <Tab value={2} label="Yield Curve" icon={<ShowChart />} />
              <Tab value={3} label="Credit Spreads" icon={<TrendingDown />} />
              <Tab value={4} label="Scenarios" icon={<Flag />} />
            </Tabs>
          </Box>

          {/* TAB 0: Recession Model */}
          <TabPanel value={tabValue} index={0}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader
                    title="Advanced Recession Probability Model"
                    subheader="Multi-factor analysis: Yield Curve (35%), Credit Spreads (25%), Labor Market (20%), Monetary Policy (15%), Volatility (5%)"
                    action={
                      <Chip
                        label={`${economicData.riskLevel} Risk`}
                        color={getRiskColor(economicData.riskLevel)}
                      />
                    }
                  />
                  <CardContent>
                    <Typography variant="h3" color="primary" gutterBottom>
                      {economicData.riskIndicator} {economicData.recessionProbability}% Probability
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={economicData.recessionProbability}
                      color={
                        economicData.recessionProbability > 60
                          ? "error"
                          : economicData.recessionProbability > 35
                            ? "warning"
                            : "success"
                      }
                      sx={{ mb: 3, height: 12 }}
                    />
                    <Typography variant="body1" paragraph>
                      {economicData.recessionAnalysis?.summary}
                    </Typography>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="h6" gutterBottom>
                      📊 Model Factors
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      {economicData.recessionAnalysis?.factors?.map((factor, idx) => (
                        <Typography key={idx} variant="body2" sx={{ mb: 1 }}>
                          {factor}
                        </Typography>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={4}>
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Forecast Models" titleTypographyProps={{ variant: "h6" }} />
                      <CardContent>
                        {economicData.forecastModels?.map((model, idx) => (
                          <Box key={idx} mb={2}>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2">{model.name}</Typography>
                              <Typography variant="body2" fontWeight="bold">
                                {model.probability}%
                              </Typography>
                            </Box>
                            <LinearProgress variant="determinate" value={model.probability} />
                            <Typography variant="caption" color="text.secondary">
                              Confidence: {model.confidence}%
                            </Typography>
                          </Box>
                        ))}
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Key Indicators" titleTypographyProps={{ variant: "h6" }} />
                      <CardContent>
                        <Typography variant="body2">
                          <strong>Yield Curve (2y10y):</strong> {formatBasisPoints(economicData.keyRecessionIndicators?.yieldCurveSpread2y10y)} bps
                        </Typography>
                        <Typography variant="body2">
                          <strong>HY Spread:</strong> {formatBasisPoints(economicData.keyRecessionIndicators?.highYieldSpread)} bps
                        </Typography>
                        <Typography variant="body2">
                          <strong>IG Spread:</strong> {formatBasisPoints(economicData.keyRecessionIndicators?.investmentGradeSpread)} bps
                        </Typography>
                        <Typography variant="body2">
                          <strong>Fed Rate:</strong> {formatPercent(economicData.keyRecessionIndicators?.fedFundsRate)}%
                        </Typography>
                        <Typography variant="body2">
                          <strong>VIX:</strong> {formatPercent(economicData.keyRecessionIndicators?.vix)}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </TabPanel>

          {/* TAB 1: Leading Indicators */}
          <TabPanel value={tabValue} index={1}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Leading Economic Indicators" />
                  <CardContent>
                    <TableContainer>
                      <Table>
                        <TableHead>
                          <TableRow>
                            <TableCell>Indicator</TableCell>
                            <TableCell align="right">Value</TableCell>
                            <TableCell align="right">Signal</TableCell>
                            <TableCell>Description</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {economicData.leadingIndicators?.map((indicator, idx) => (
                            <TableRow key={idx}>
                              <TableCell>
                                <strong>{indicator.name}</strong>
                              </TableCell>
                              <TableCell align="right">{indicator.value}</TableCell>
                              <TableCell align="right">
                                <Chip
                                  label={indicator.signal}
                                  color={
                                    indicator.signal === "Positive"
                                      ? "success"
                                      : indicator.signal === "Negative"
                                        ? "error"
                                        : "default"
                                  }
                                  size="small"
                                />
                              </TableCell>
                              <TableCell>{indicator.description}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card>
                  <CardHeader title="📅 Upcoming Economic Events" />
                  <CardContent>
                    <TableContainer>
                      <Table>
                        <TableHead>
                          <TableRow>
                            <TableCell>Date</TableCell>
                            <TableCell>Event</TableCell>
                            <TableCell>Category</TableCell>
                            <TableCell>Importance</TableCell>
                            <TableCell>Forecast</TableCell>
                            <TableCell>Previous</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {economicData.upcomingEvents?.length > 0 ? (
                            economicData.upcomingEvents.map((event, idx) => (
                              <TableRow key={idx}>
                                <TableCell>{event.date}</TableCell>
                                <TableCell>{event.event}</TableCell>
                                <TableCell>{event.category}</TableCell>
                                <TableCell>
                                  <Chip
                                    label={event.importance}
                                    color={
                                      event.importance === "high"
                                        ? "error"
                                        : event.importance === "medium"
                                          ? "warning"
                                          : "default"
                                    }
                                    size="small"
                                  />
                                </TableCell>
                                <TableCell>{event.forecast}</TableCell>
                                <TableCell>{event.previous}</TableCell>
                              </TableRow>
                            ))
                          ) : (
                            <TableRow>
                              <TableCell colSpan={6} align="center">
                                No upcoming events
                              </TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </TabPanel>

          {/* TAB 2: Yield Curve */}
          <TabPanel value={tabValue} index={2}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Card>
                  <CardHeader
                    title="Treasury Yield Curve"
                    subheader={
                      economicData.yieldCurve?.isInverted
                        ? "🔴 INVERTED - Recession signal detected"
                        : "🟢 NORMAL - Healthy economic conditions"
                    }
                  />
                  <CardContent>
                    {economicData.yieldCurveData?.length > 0 ? (
                      <ResponsiveContainer width="100%" height={400}>
                        <LineChart data={economicData.yieldCurveData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="maturity" />
                          <YAxis />
                          <Tooltip formatter={(value) => `${value}%`} />
                          <Line type="monotone" dataKey="yield" stroke="#1976d2" strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <Alert severity="warning">No yield curve data available</Alert>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Yield Curve Analysis" />
                  <CardContent>
                    <Typography variant="body2" paragraph>
                      <strong>2y10y Spread:</strong> {formatBasisPoints(economicData.yieldCurve?.spread2y10y)} bps
                    </Typography>
                    <Typography variant="body2" paragraph>
                      <strong>3m10y Spread:</strong> {formatBasisPoints(economicData.yieldCurve?.spread3m10y)} bps
                    </Typography>
                    <Typography variant="body2" paragraph>
                      <strong>Inversion Status:</strong> {economicData.yieldCurve?.isInverted ? "🔴 INVERTED" : "🟢 NORMAL"}
                    </Typography>
                    <Typography variant="body2" paragraph>
                      <strong>Historical Accuracy:</strong> {economicData.yieldCurve?.historicalAccuracy}%
                    </Typography>
                    <Typography variant="body2">
                      <strong>Average Lead Time:</strong> {economicData.yieldCurve?.averageLeadTime} months
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Interpretation" />
                  <CardContent>
                    <Typography variant="body2">{economicData.yieldCurve?.interpretation}</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </TabPanel>

          {/* TAB 3: Credit Spreads */}
          <TabPanel value={tabValue} index={3}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="High Yield Spreads" />
                  <CardContent>
                    <Typography variant="h4" color="primary" gutterBottom>
                      {economicData.creditSpreads?.highYield?.oas || "N/A"} bps
                    </Typography>
                    <Chip
                      label={economicData.creditSpreads?.highYield?.signal || "N/A"}
                      size="small"
                      sx={{ mb: 2 }}
                    />
                    <Typography variant="body2" color="text.secondary">
                      {economicData.creditSpreads?.highYield?.historicalContext}
                    </Typography>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="body2">
                      <strong>BB-Rated:</strong> {economicData.creditSpreads?.highYieldByRating?.bbRated?.oas || "N/A"} bps
                    </Typography>
                    <Typography variant="body2">
                      <strong>B-Rated:</strong> {economicData.creditSpreads?.highYieldByRating?.bRated?.oas || "N/A"} bps
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Investment Grade Spreads" />
                  <CardContent>
                    <Typography variant="h4" color="primary" gutterBottom>
                      {economicData.creditSpreads?.investmentGrade?.oas || "N/A"} bps
                    </Typography>
                    <Chip
                      label={economicData.creditSpreads?.investmentGrade?.signal || "N/A"}
                      size="small"
                      sx={{ mb: 2 }}
                    />
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="body2">
                      <strong>AAA-Rated:</strong> {economicData.creditSpreads?.investmentGradeByRating?.aaaRated?.oas || "N/A"} bps
                    </Typography>
                    <Typography variant="body2">
                      <strong>BBB-Rated:</strong> {economicData.creditSpreads?.investmentGradeByRating?.bbbRated?.oas || "N/A"} bps
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Financial Conditions Index" />
                  <CardContent>
                    <Box mb={2}>
                      <Typography variant="subtitle2" color="text.secondary">
                        FCI Value
                      </Typography>
                      <Typography variant="h3">
                        {economicData.financialConditionsIndex?.value || "N/A"}
                      </Typography>
                      <Typography variant="body2">
                        Level: {economicData.financialConditionsIndex?.level || "Neutral"}
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </TabPanel>

          {/* TAB 4: Scenarios */}
          <TabPanel value={tabValue} index={4}>
            <Grid container spacing={3}>
              {economicData.scenarios?.map((scenario, idx) => (
                <Grid item xs={12} md={4} key={idx}>
                  <Card
                    sx={{
                      borderLeft: `4px solid ${
                        scenario.name === "Bull Case"
                          ? "#4caf50"
                          : scenario.name === "Bear Case"
                            ? "#f44336"
                            : "#ff9800"
                      }`,
                    }}
                  >
                    <CardHeader
                      title={scenario.name}
                      subheader={`Probability: ${scenario.probability}%`}
                    />
                    <CardContent>
                      <Typography variant="body2" paragraph>
                        {scenario.description}
                      </Typography>
                      <Divider sx={{ my: 1 }} />
                      <Typography variant="body2">
                        <strong>GDP Growth:</strong> {formatPercent(scenario.gdpGrowth)}%
                      </Typography>
                      <Typography variant="body2">
                        <strong>Unemployment:</strong> {formatPercent(scenario.unemployment)}%
                      </Typography>
                      <Typography variant="body2">
                        <strong>Fed Rate:</strong> {formatPercent(scenario.fedRate)}%
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </TabPanel>
        </>
      )}
    </Container>
  );
};

export default EconomicModeling;
