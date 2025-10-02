import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Grid,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  ExpandMore,
  CheckCircle,
  Error as ErrorIcon,
  Warning,
  Info,
  Refresh,
  Storage,
  Api,
  Cloud,
  Speed,
} from "@mui/icons-material";

// Import API functions
import {
  healthCheck,
  getTechnicalData,
  getStocks,
  getMarketOverview,
  testApiConnection,
  screenStocks,
  getBuySignals,
  getSellSignals,
  getNaaimData,
  getFearGreedData,
  getApiConfig,
  getDiagnosticInfo,
  getCurrentBaseURL,
  api,
} from "../services/api";

function isObject(val) {
  return val && typeof val === "object" && !Array.isArray(val);
}

function ServiceHealth() {
  const [environmentInfo, setEnvironmentInfo] = useState({});
  const [testResults, setTestResults] = useState({});
  const [testingInProgress, setTestingInProgress] = useState(false);
  const [componentError, setComponentError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Memoize diagnosticInfo to prevent infinite re-renders
  const diagnosticInfo = useMemo(() => {
    try {
      return getDiagnosticInfo();
    } catch (error) {
      console.error("Error getting diagnostic info:", error);
      return {};
    }
  }, []);

  // Memoize other API config calls to prevent infinite re-renders
  const _apiConfig = useMemo(() => {
    try {
      return getApiConfig();
    } catch (error) {
      console.error("Error getting API config:", error);
      return {};
    }
  }, []);
  const _currentBaseURL = useMemo(() => {
    try {
      return getCurrentBaseURL();
    } catch (error) {
      console.error("Error getting current base URL:", error);
      return "";
    }
  }, []);

  // Component error handler
  useEffect(() => {
    const handleError = (event) => {
      console.error("ServiceHealth component error:", event.error);
      setComponentError(event.error.message);
    };

    window.addEventListener("error", handleError);
    return () => window.removeEventListener("error", handleError);
  }, []);

  // ECS task monitoring - check status of scheduled tasks
  const {
    data: ecsTasks,
    isLoading: ecsLoading,
    error: ecsError,
    refetch: refetchEcs,
  } = useQuery({
    queryKey: ["ecsTasks"],
    queryFn: async () => {
      try {
        const response = await api.get("/health/ecs-tasks", {
          timeout: 10000,
          validateStatus: (status) => status < 500,
        });
        return response?.data?.success ? response.data : response?.data;
      } catch (error) {
        console.error("ECS tasks check failed:", error);
        return {
          error: true,
          message: error.message || "Unknown ECS tasks error",
          timestamp: new Date().toISOString(),
        };
      }
    },
    refetchInterval: 60000, // Refresh every minute
    retry: 1,
    staleTime: 30000,
    enabled: true,
    onError: (error) => {
      console.error("React Query ECS tasks error:", error);
    },
  });

  // Cached database health check - uses the backend's cached health_status table
  const {
    data: dbHealth,
    isLoading: dbLoading,
    error: dbError,
    refetch: refetchDb,
  } = useQuery({
    queryKey: ["databaseHealth"],
    queryFn: async () => {
      try {
        if (import.meta.env && import.meta.env.DEV)
          console.log("Starting cached database health check...");

        // Use the standard api instance but with better error handling
        const response = await api.get("/health/database", {
          timeout: 60000, // 60 second timeout (matches Lambda timeout)
          validateStatus: (status) => status < 500, // Don't throw on 4xx errors
        });

        if (import.meta.env && import.meta.env.DEV)
          console.log("Database health response:", response?.data);

        // Extract the actual data from the success wrapper
        const healthData = response?.data?.success
          ? response?.data.data
          : response?.data;

        if (import.meta.env && import.meta.env.DEV)
          console.log("Response structure:", {
            hasData: !!healthData,
            hasDatabase: !!healthData?.database,
            hasTables: !!healthData?.database?.tables,
            hasSummary: !!healthData?.database?.summary,
            tableCount: healthData?.database?.tables
              ? Object.keys(healthData.database.tables).length
              : 0,
          });

        // Ensure we return a proper object structure
        if (healthData && typeof healthData === "object") {
          return healthData;
        } else {
          throw new Error(
            "Invalid response structure from database health endpoint"
          );
        }
      } catch (error) {
        console.error("Database health check failed:", error);
        console.error("Error details:", {
          message: error.message,
          response: error.response?.data,
          status: error.response?.status,
        });

        // Return a structured error object instead of throwing
        return {
          error: true,
          message: error.message || "Unknown database health error",
          details:
            error.response?.data ||
            error.response?.status ||
            "No additional details",
          timestamp: new Date().toISOString(),
          // Provide fallback data structure that matches the expected format
          database: {
            status: "error",
            currentTime: new Date().toISOString(),
            postgresVersion: "unknown",
            tables: {},
            summary: {
              total_tables: 0,
              healthy_tables: 0,
              stale_tables: 0,
              empty_tables: 0,
              error_tables: 1,
              missing_tables: 0,
              total_records: 0,
              total_missing_data: 0,
            },
          },
        };
      }
    },
    refetchInterval: false,
    retry: 1,
    staleTime: 30000,
    enabled: true, // Auto-run on mount
    // Add error handling to prevent React Query from throwing
    onError: (error) => {
      console.error("React Query database health error:", error);
    },
  });

  // Simplified endpoint tests - only test essential endpoints
  const endpoints = useMemo(
    () => [
      { name: "Health Check", fn: () => healthCheck() },
      { name: "API Connection", fn: () => testApiConnection() },
      { name: "Stocks", fn: () => getStocks({ limit: 5 }) },
      {
        name: "Technical Data",
        fn: () => getTechnicalData("daily", { limit: 5 }),
      },
      {
        name: "Market Overview",
        fn: () => getMarketOverview(),
      },
      {
        name: "Stock Screener",
        fn: () => screenStocks({ limit: 5 }),
      },
      { name: "Buy Signals", fn: () => getBuySignals() },
      { name: "Sell Signals", fn: () => getSellSignals() },
      {
        name: "NAAIM Data",
        fn: () => getNaaimData({ limit: 5 }),
      },
      {
        name: "Fear & Greed",
        fn: () => getFearGreedData({ limit: 5 }),
      },
    ],
    []
  );

  // Test all endpoints
  const testAllEndpoints = useCallback(async () => {
    // Skip API calls in test environment to prevent hanging
    if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
      setTestingInProgress(false);
      return;
    }

    setTestingInProgress(true);
    const results = {};

    if (import.meta.env && import.meta.env.DEV)
      console.log("Starting endpoint tests...");

    // Test each endpoint with timeout and error handling
    for (const endpoint of endpoints) {
      try {
        const startTime = Date.now();
        if (import.meta.env && import.meta.env.DEV)
          console.log(`Testing ${endpoint.name}...`);

        await Promise.race([
          endpoint.fn(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("Timeout")), 10000)
          ),
        ]);

        const endTime = Date.now();
        results[endpoint.name] = {
          status: "success",
          response: "OK",
          responseTime: endTime - startTime,
          critical: endpoint.critical,
        };
        if (import.meta.env && import.meta.env.DEV)
          console.log(`✅ ${endpoint.name} passed (${endTime - startTime}ms)`);
      } catch (error) {
        console.error(`❌ ${endpoint.name} failed:`, error);
        results[endpoint.name] = {
          status: "error",
          error: error.message || "Unknown error",
          responseTime: 0,
          critical: endpoint.critical,
        };
      }
    }

    setTestResults(results);
    setTestingInProgress(false);
    if (import.meta.env && import.meta.env.DEV)
      console.log("Endpoint tests completed:", results);
  }, [endpoints]);

  // Service health query
  const {
    data: healthData,
    isLoading: healthLoading,
    error: healthError,
    refetch: refetchHealth,
  } = useQuery({
    queryKey: ["serviceHealth"],
    queryFn: async () => {
      if (import.meta.env && import.meta.env.DEV)
        console.log("Fetching service health...");
      try {
        const response = await api.get("/health");
        if (import.meta.env && import.meta.env.DEV)
          console.log("Service health response:", response?.data);
        return response?.data;
      } catch (error) {
        console.error("Service health error:", error);
        throw error;
      }
    },
    refetchInterval: false,
    retry: 1,
    staleTime: 30000,
    enabled: true,
  });

  useEffect(() => {
    // Run API tests automatically when component mounts
    testAllEndpoints();
  }, [testAllEndpoints]);

  useEffect(() => {
    const env = {
      Frontend: {
        API_URL: process.env.REACT_APP_API_URL || "Not set",
        Environment: process.env.NODE_ENV || "development",
        Build_Time: process.env.REACT_APP_BUILD_TIME || "Unknown",
        Version: process.env.REACT_APP_VERSION || "1.0.0",
      },
      Browser: {
        User_Agent: navigator.userAgent,
        Language: navigator.language,
        Platform: navigator.platform,
        Online: navigator.onLine,
        Cookies_Enabled: navigator.cookieEnabled,
      },
      Runtime: {
        React_Version: React.version,
        Timestamp: new Date().toISOString(),
        Timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      },
    };

    setEnvironmentInfo(env);
  }, []);

  // Safe data extraction
  const safeHealthData = isObject(healthData) ? healthData : {};
  const safeDbHealth = isObject(dbHealth) ? dbHealth : {};
  const safeTestResults = isObject(testResults) ? testResults : {};
  const safeEnvironmentInfo = isObject(environmentInfo) ? environmentInfo : {};
  const safeDiagnosticInfo = isObject(diagnosticInfo) ? diagnosticInfo : {};

  const getStatusIcon = (status) => {
    switch (status) {
      case "success":
        return <CheckCircle color="success" />;
      case "error":
        return <ErrorIcon color="error" />;
      case "warning":
        return <Warning color="warning" />;
      default:
        return <Refresh />;
    }
  };

  const _handleRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([refetchDb(), refetchHealth(), testAllEndpoints()]);
    } catch (error) {
      console.error("Failed to refresh service health:", error);
      // Don't throw - just log the error
    } finally {
      setRefreshing(false);
    }
  };

  const _formatTimestamp = (timestamp) => {
    if (!timestamp) return "Unknown";
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMinutes = Math.floor(diffMs / (1000 * 60));

    if (diffMinutes < 1) {
      return "Just now";
    } else if (diffMinutes < 60) {
      return `${diffMinutes} minute${diffMinutes > 1 ? "s" : ""} ago`;
    }
  };

  // Early return if component has error
  if (componentError) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="error">
          <Typography variant="h6">Service Health Error</Typography>
          <Typography variant="body2">{componentError}</Typography>
          <Button onClick={() => window.location.reload()} sx={{ mt: 2 }}>
            Reload Page
          </Button>
        </Alert>
      </Container>
    );
  }

  // Refresh health status background job
  const refreshHealthStatus = async () => {
    try {
      setRefreshing(true);

      // Just refetch the health data since there's no update-status endpoint
      // The health endpoint already provides comprehensive status
      await refetchDb();
    } catch (error) {
      console.error("Failed to refresh health status:", error);
      // Don't throw - just log the error
    } finally {
      setRefreshing(false);
    }
  };

  // Safe data extraction (all safe variables already defined above)

  const getStatusColor = (status) => {
    switch (status) {
      case "success":
      case "healthy":
      case "connected":
        return "success";
      case "error":
      case "failed":
      case "disconnected":
        return "error";
      case "warning":
      case "stale":
      case "incomplete":
        return "warning";
      case "empty":
        return "info";
      default:
        return "default";
    }
  };

  const formatNumber = (num) => {
    if (num === null || num === undefined) return "N/A";
    return new Intl.NumberFormat().format(num);
  };

  const formatDate = (dateString) => {
    if (!dateString) return "N/A";
    return new Date(dateString).toLocaleString();
  };

  const formatTimeAgo = (dateString) => {
    if (!dateString) return "N/A";
    const now = new Date();
    const date = new Date(dateString);
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) {
      return `${diffDays} day${diffDays > 1 ? "s" : ""} ago`;
    } else if (diffHours > 0) {
      return `${diffHours} hour${diffHours > 1 ? "s" : ""} ago`;
    } else {
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      return `${diffMinutes} minute${diffMinutes > 1 ? "s" : ""} ago`;
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Service Health Dashboard
        </Typography>
        <Typography variant="subtitle1" color="textSecondary">
          Monitor system status, API health, and data integrity
        </Typography>
      </Box>

      {/* Overall Status */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent sx={{ textAlign: "center" }}>
              {healthLoading ? (
                <CircularProgress />
              ) : healthError ? (
                <>
                  <ErrorIcon color="error" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h6" color="error">
                    Service Down
                  </Typography>
                </>
              ) : (
                <>
                  <CheckCircle color="success" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h6" color="success.main">
                    Service Healthy
                  </Typography>
                </>
              )}
              <Button
                variant="outlined"
                size="small"
                startIcon={<Refresh />}
                onClick={refetchHealth}
                sx={{ mt: 1 }}
                disabled={refreshing}
              >
                {refreshing ? "Refreshing..." : "Refresh Health Status"}
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent sx={{ textAlign: "center" }}>
              <Api sx={{ fontSize: 40, mb: 1, color: "primary.main" }} />
              <Typography variant="h6">API Gateway</Typography>
              <Typography variant="body2" color="textSecondary">
                {safeDiagnosticInfo?.isConfigured
                  ? "Configured"
                  : "Not Configured"}
              </Typography>
              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                {safeDiagnosticInfo?.urlsMatch ? "URLs Match" : "URL Mismatch"}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent sx={{ textAlign: "center" }}>
              <Storage sx={{ fontSize: 40, mb: 1, color: "primary.main" }} />
              <Typography variant="h6">Database</Typography>
              <Typography variant="body2" color="textSecondary">
                {dbLoading
                  ? "Checking..."
                  : dbError
                    ? "Error"
                    : safeDbHealth?.database?.status === "connected"
                      ? "Connected"
                      : safeDbHealth?.database?.status === "disconnected"
                        ? "Disconnected"
                        : safeDbHealth?.error
                          ? "Error"
                          : "Unknown"}
              </Typography>
              {dbError && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  <Typography variant="subtitle2">
                    Failed to load database health:
                  </Typography>
                  <Typography variant="body2" sx={{ wordBreak: "break-all" }}>
                    {typeof dbError === "string"
                      ? dbError
                      : dbError?.message || "Unknown error"}
                  </Typography>
                </Alert>
              )}
              {safeDbHealth?.error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  <Typography variant="subtitle2">Database Error:</Typography>
                  <Typography variant="body2" sx={{ wordBreak: "break-all" }}>
                    {safeDbHealth.message || "Unknown error"}
                  </Typography>
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent sx={{ textAlign: "center" }}>
              <Cloud sx={{ fontSize: 40, mb: 1, color: "primary.main" }} />
              <Typography variant="h6">Environment</Typography>
              <Typography variant="body2" color="textSecondary">
                {(() => {
                  const env =
                    (import.meta.env && import.meta.env.VITE_ENV) ||
                    (import.meta.env && import.meta.env.MODE) ||
                    "";
                  if (env.toLowerCase().startsWith("prod")) return "Production";
                  if (env.toLowerCase().startsWith("stag")) return "Staging";
                  if (env.toLowerCase().startsWith("dev")) return "Development";
                  if (env) return env.charAt(0).toUpperCase() + env.slice(1);
                  return "Production";
                })()}
              </Typography>
              <Typography
                variant="caption"
                display="block"
                sx={{ mt: 1 }}
                title={(import.meta.env && import.meta.env.VITE_API_URL) || ""}
              >
                {import.meta.env && import.meta.env.VITE_API_URL
                  ? `API: ${import.meta.env.VITE_API_URL}`
                  : ""}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Detailed Health Information */}
      <Grid container spacing={3}>
        {/* API Health */}
        <Grid item xs={12}>
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography variant="h6">
                <Api sx={{ mr: 1, verticalAlign: "middle" }} />
                API Health
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              {safeHealthData && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Status: {safeHealthData.status}
                  </Typography>
                  <Typography
                    variant="body2"
                    color="textSecondary"
                    gutterBottom
                  >
                    Last Updated:{" "}
                    {new Date(safeHealthData.timestamp).toLocaleString()}
                  </Typography>

                  {safeHealthData.api && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2">
                        API Information:
                      </Typography>
                      <Typography variant="body2">
                        Version: {safeHealthData.api.version}
                      </Typography>
                      <Typography variant="body2">
                        Environment: {safeHealthData.api.environment}
                      </Typography>
                    </Box>
                  )}
                </Box>
              )}

              <Box sx={{ mt: 2 }}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<Speed />}
                  onClick={testAllEndpoints}
                  disabled={testingInProgress}
                >
                  {testingInProgress ? "Testing..." : "Test All Endpoints"}
                </Button>
              </Box>

              {Object.keys(safeTestResults).length > 0 && (
                <TableContainer component={Paper} sx={{ mt: 2 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Endpoint</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Response Time</TableCell>
                        <TableCell>Error</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {Object.entries(safeTestResults).map(([name, result]) => (
                        <TableRow key={name}>
                          <TableCell>{name}</TableCell>
                          <TableCell>
                            <Chip
                              icon={getStatusIcon(result?.status)}
                              label={result?.status || "Unknown"}
                              color={getStatusColor(result?.status)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            {result.responseTime
                              ? `${result.responseTime}ms`
                              : "-"}
                          </TableCell>
                          <TableCell>{result.error || "-"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </AccordionDetails>
          </Accordion>
        </Grid>

        {/* ECS Scheduled Tasks Status - Only show in production AWS environment */}
        {ecsTasks?.environment !== "local" && (
          <Grid item xs={12}>
            <Accordion defaultExpanded>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6">
                  <Cloud sx={{ mr: 1, verticalAlign: "middle" }} />
                  Scheduled Tasks Status
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
              <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<Refresh />}
                  onClick={() => refetchEcs()}
                >
                  Refresh
                </Button>
              </Box>

              {ecsLoading && (
                <Box sx={{ display: "flex", justifyContent: "center", p: 2 }}>
                  <CircularProgress size={24} />
                  <Typography sx={{ ml: 2 }}>
                    Loading scheduled tasks status...
                  </Typography>
                </Box>
              )}

              {ecsError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <Typography variant="subtitle2">
                    Failed to load ECS tasks status:
                  </Typography>
                  <Typography variant="body2" sx={{ wordBreak: "break-all" }}>
                    {typeof ecsError === "string"
                      ? ecsError
                      : ecsError?.message || "Unknown error"}
                  </Typography>
                </Alert>
              )}

              {!ecsLoading && !ecsError && ecsTasks && ecsTasks.tasks && (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Task Name</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Last Run</TableCell>
                        <TableCell>Freshness</TableCell>
                        <TableCell>Details</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {Object.entries(ecsTasks.tasks).map(([taskName, taskData]) => (
                        <TableRow key={taskName}>
                          <TableCell>
                            <Typography variant="body2" fontWeight="bold">
                              {taskName}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              icon={
                                taskData.status === "success" ? (
                                  <CheckCircle />
                                ) : taskData.status === "failure" ? (
                                  <ErrorIcon />
                                ) : taskData.status === "never_run" ? (
                                  <Info />
                                ) : (
                                  <Warning />
                                )
                              }
                              label={taskData.status || "unknown"}
                              color={
                                taskData.status === "success"
                                  ? "success"
                                  : taskData.status === "failure"
                                  ? "error"
                                  : taskData.status === "never_run"
                                  ? "default"
                                  : "warning"
                              }
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            {taskData.last_run ? (
                              <Tooltip title={new Date(taskData.last_run).toLocaleString()}>
                                <Typography variant="body2">
                                  {taskData.hours_since_run !== undefined
                                    ? `${taskData.hours_since_run}h ago`
                                    : new Date(taskData.last_run).toLocaleDateString()}
                                </Typography>
                              </Tooltip>
                            ) : (
                              <Typography variant="body2" color="text.secondary">
                                Never
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell>
                            {taskData.freshness && (
                              <Chip
                                label={taskData.freshness}
                                color={
                                  taskData.freshness === "current"
                                    ? "success"
                                    : taskData.freshness === "warning"
                                    ? "warning"
                                    : "error"
                                }
                                size="small"
                              />
                            )}
                          </TableCell>
                          <TableCell>
                            {taskData.error_message ? (
                              <Tooltip title={taskData.error_message}>
                                <Typography variant="body2" color="error" noWrap>
                                  {taskData.error_message.substring(0, 50)}...
                                </Typography>
                              </Tooltip>
                            ) : taskData.message ? (
                              <Typography variant="body2" color="text.secondary">
                                {taskData.message}
                              </Typography>
                            ) : taskData.exit_code !== null && taskData.exit_code !== undefined ? (
                              <Typography variant="body2">
                                Exit code: {taskData.exit_code}
                              </Typography>
                            ) : (
                              "-"
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}

              {!ecsLoading && !ecsError && (!ecsTasks || !ecsTasks.tasks || Object.keys(ecsTasks.tasks).length === 0) && (
                <Alert severity={ecsTasks?.environment === "local" ? "warning" : "info"}>
                  <Typography variant="subtitle2">
                    {ecsTasks?.environment === "local"
                      ? "ECS Task Monitoring Not Available"
                      : "No scheduled tasks configured"}
                  </Typography>
                  <Typography variant="body2">
                    {ecsTasks?.environment === "local"
                      ? "Scheduled task monitoring is only available in AWS production environment. View the AWS production site to see task status."
                      : "Configure scheduled tasks in GitHub Actions workflows or AWS EventBridge."}
                  </Typography>
                </Alert>
              )}
            </AccordionDetails>
          </Accordion>
        </Grid>
        )}

        {/* Database Health */}
        <Grid item xs={12}>
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography variant="h6">
                <Storage sx={{ mr: 1, verticalAlign: "middle" }} />
                Database Health
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 2 }}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<Refresh />}
                  onClick={refreshHealthStatus}
                  disabled={refreshing}
                >
                  {refreshing ? "Updating..." : "Update All Tables"}
                </Button>
              </Box>

              {dbLoading && (
                <Box sx={{ display: "flex", justifyContent: "center", p: 2 }}>
                  <CircularProgress size={24} />
                  <Typography sx={{ ml: 2 }}>
                    Loading database health...
                  </Typography>
                </Box>
              )}

              {dbError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <Typography variant="subtitle2">
                    Failed to load database health:
                  </Typography>
                  <Typography variant="body2" sx={{ wordBreak: "break-all" }}>
                    {typeof dbError === "string"
                      ? dbError
                      : dbError?.message || "Unknown error"}
                  </Typography>
                </Alert>
              )}

              {safeDbHealth && (
                <Box>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      Database Status:
                    </Typography>
                    <Typography variant="body2">
                      Status: {safeDbHealth.database?.status || "Unknown"}
                    </Typography>
                    {safeDbHealth.database?.currentTime && (
                      <Typography variant="body2">
                        Current Time:{" "}
                        {new Date(
                          safeDbHealth.database.currentTime
                        ).toLocaleString()}
                      </Typography>
                    )}
                    {safeDbHealth.database?.postgresVersion && (
                      <Typography variant="body2">
                        PostgreSQL Version:{" "}
                        {safeDbHealth.database.postgresVersion}
                      </Typography>
                    )}
                  </Box>

                  {/* Backend error/message display */}
                  {safeDbHealth.error ||
                  safeDbHealth.message ||
                  safeDbHealth.details ? (
                    <Alert severity="error" sx={{ mb: 2 }}>
                      <Typography variant="subtitle2">
                        Backend Error:
                      </Typography>
                      {safeDbHealth.error && (
                        <Typography
                          variant="body2"
                          sx={{ wordBreak: "break-all" }}
                        >
                          <b>Error:</b> {safeDbHealth.error}
                        </Typography>
                      )}
                      {safeDbHealth.message && (
                        <Typography
                          variant="body2"
                          sx={{ wordBreak: "break-all" }}
                        >
                          <b>Message:</b> {safeDbHealth.message}
                        </Typography>
                      )}
                      {safeDbHealth.details && (
                        <Typography
                          variant="body2"
                          sx={{ wordBreak: "break-all" }}
                        >
                          <b>Details:</b> {safeDbHealth.details}
                        </Typography>
                      )}
                    </Alert>
                  ) : null}

                  {/* Summary Statistics */}
                  {safeDbHealth.database?.summary && (
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>
                        Summary:
                      </Typography>
                      <Grid container spacing={1}>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="text.secondary">
                            Total Tables:{" "}
                            {safeDbHealth.database.summary.total_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="success.main">
                            Healthy:{" "}
                            {safeDbHealth.database.summary.healthy_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="text.secondary">
                            Stale: {safeDbHealth.database.summary.stale_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="error.main">
                            Errors: {safeDbHealth.database.summary.error_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="info.dark">
                            Empty: {safeDbHealth.database.summary.empty_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="text.secondary">
                            Missing:{" "}
                            {safeDbHealth.database.summary.missing_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="text.secondary">
                            Total Records:{" "}
                            {formatNumber(
                              safeDbHealth.database.summary.total_records
                            )}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="text.secondary">
                            Missing Data:{" "}
                            {formatNumber(
                              safeDbHealth.database.summary.total_missing_data
                            )}
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>
                  )}

                  {/* Detailed Table List */}
                  {safeDbHealth.database?.tables &&
                    Object.keys(safeDbHealth.database.tables).length > 0 && (
                      <Box sx={{ mt: 2 }}>
                        <Typography variant="subtitle2" gutterBottom>
                          Table Details (
                          {Object.keys(safeDbHealth.database.tables).length}{" "}
                          tables monitored):
                        </Typography>
                        <TableContainer
                          component={Paper}
                          sx={{ maxHeight: 600 }}
                        >
                          <Table size="small" stickyHeader>
                            <TableHead>
                              <TableRow>
                                <TableCell>Table</TableCell>
                                <TableCell align="right">Records</TableCell>
                                <TableCell>Status</TableCell>
                                <TableCell>Last Updated</TableCell>
                                <TableCell>Missing Data</TableCell>
                                <TableCell>Last Checked</TableCell>
                                <TableCell>Error</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {Object.entries(safeDbHealth.database.tables)
                                .sort(([a], [b]) => a.localeCompare(b))
                                .map(([tableName, tableData]) => (
                                  <TableRow
                                    key={tableName}
                                    sx={{
                                      "&:hover": {
                                        backgroundColor: "rgba(0, 0, 0, 0.04)",
                                      },
                                    }}
                                  >
                                    <TableCell component="th" scope="row">
                                      <Typography
                                        variant="body2"
                                        fontFamily="monospace"
                                        fontWeight={600}
                                      >
                                        {tableName}
                                      </Typography>
                                    </TableCell>
                                    <TableCell align="right">
                                      <Typography
                                        variant="body2"
                                        fontWeight={600}
                                      >
                                        {formatNumber(tableData.record_count)}
                                      </Typography>
                                    </TableCell>
                                    <TableCell>
                                      <Box
                                        sx={{
                                          display: "flex",
                                          gap: 0.5,
                                          alignItems: "center",
                                        }}
                                      >
                                        <Chip
                                          icon={getStatusIcon(tableData.status)}
                                          label={tableData.status}
                                          color={getStatusColor(
                                            tableData.status
                                          )}
                                          size="small"
                                          sx={{ minWidth: 80 }}
                                        />
                                        {tableData.is_stale && (
                                          <Chip
                                            label="Stale"
                                            color="warning"
                                            size="small"
                                          />
                                        )}
                                      </Box>
                                    </TableCell>
                                    <TableCell>
                                      <Box>
                                        <Typography variant="body2">
                                          {formatDate(tableData.last_updated)}
                                        </Typography>
                                        <Typography
                                          variant="caption"
                                          color="text.secondary"
                                        >
                                          {formatTimeAgo(
                                            tableData.last_updated
                                          )}
                                        </Typography>
                                      </Box>
                                    </TableCell>
                                    <TableCell align="right">
                                      {tableData.missing_data_count > 0 ? (
                                        <Typography
                                          variant="body2"
                                          color="text.secondary"
                                          fontWeight={600}
                                        >
                                          {formatNumber(
                                            tableData.missing_data_count
                                          )}
                                        </Typography>
                                      ) : (
                                        <Typography
                                          variant="body2"
                                          color="success.main"
                                        >
                                          0
                                        </Typography>
                                      )}
                                    </TableCell>
                                    <TableCell>
                                      <Typography variant="body2">
                                        {formatDate(tableData.last_checked)}
                                      </Typography>
                                    </TableCell>
                                    <TableCell>
                                      {tableData.error && (
                                        <Tooltip title={tableData.error}>
                                          <Typography
                                            variant="body2"
                                            color="error"
                                            sx={{
                                              maxWidth: 200,
                                              overflow: "hidden",
                                              textOverflow: "ellipsis",
                                              cursor: "help",
                                            }}
                                          >
                                            {tableData.error.length > 30
                                              ? `${tableData.error.substring(0, 30)}...`
                                              : tableData.error}
                                          </Typography>
                                        </Tooltip>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </Box>
                    )}

                  {/* Show if no tables found */}
                  {(!safeDbHealth.database?.tables ||
                    Object.keys(safeDbHealth.database.tables).length === 0) && (
                    <Alert severity="warning" sx={{ mt: 2 }}>
                      <Typography variant="subtitle2">
                        No table data found
                      </Typography>
                      <Typography variant="body2">
                        The database health check did not return any table
                        information. This could mean the health_status table is
                        empty or the backend is not properly configured.
                      </Typography>
                    </Alert>
                  )}

                  {safeDbHealth.database?.note && (
                    <Alert severity="info" sx={{ mt: 2 }}>
                      {safeDbHealth.database.note}
                    </Alert>
                  )}
                </Box>
              )}
            </AccordionDetails>
          </Accordion>
        </Grid>

      </Grid>
    </Container>
  );
}

export default ServiceHealth;
