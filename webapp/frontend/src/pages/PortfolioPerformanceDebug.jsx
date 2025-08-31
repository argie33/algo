import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import {
  Container,
  Typography,
  CircularProgress,
  Alert,
  Card,
  CardContent,
  Button,
  Box,
  Paper,
} from "@mui/material";
import {
  getPortfolioPerformance,
  getPortfolioAnalytics,
} from "../services/api";

const PortfolioPerformanceDebug = () => {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [performanceData, setPerformanceData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [debugInfo, setDebugInfo] = useState([]);

  const addDebugInfo = useCallback((message) => {
    const timestamp = new Date().toLocaleTimeString();
    const logMessage = `${timestamp}: ${message}`;
    console.log("🐛 DEBUG:", logMessage);
    setDebugInfo((prev) => [...prev, logMessage]);
  }, []);

  useEffect(() => {
    addDebugInfo("Component mounted");
    addDebugInfo(
      `Auth loading: ${authLoading}, Authenticated: ${isAuthenticated}, User: ${user ? user.username : "none"}`
    );
  }, [authLoading, isAuthenticated, user, addDebugInfo]);

  useEffect(() => {
    addDebugInfo(
      `Auth state changed - Loading: ${authLoading}, Authenticated: ${isAuthenticated}`
    );

    // Only fetch data when auth is not loading
    if (!authLoading) {
      addDebugInfo("Auth loading complete, attempting to fetch data");
      fetchData();
    }
  }, [authLoading, isAuthenticated, addDebugInfo, fetchData]);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      addDebugInfo("Starting data fetch...");

      // Check if we have any auth token
      const accessToken =
        localStorage.getItem("accessToken") ||
        localStorage.getItem("authToken");
      addDebugInfo(
        `Access token exists: ${!!accessToken} (length: ${accessToken ? (accessToken?.length || 0) : 0})`
      );

      // Test 1: Portfolio Performance
      addDebugInfo("Calling getPortfolioPerformance API...");
      try {
        const perfResponse = await getPortfolioPerformance("1Y");
        addDebugInfo(
          `Performance API success: ${JSON.stringify(perfResponse?.success || "unknown")}`
        );
        setPerformanceData(perfResponse);
      } catch (perfError) {
        addDebugInfo(`Performance API failed: ${perfError.message}`);
        throw perfError;
      }

      // Test 2: Portfolio Analytics
      addDebugInfo("Calling getPortfolioAnalytics API...");
      try {
        const analyticsResponse = await getPortfolioAnalytics("1Y");
        addDebugInfo(
          `Analytics API success: ${JSON.stringify(analyticsResponse?.success || "unknown")}`
        );
        setAnalyticsData(analyticsResponse);
      } catch (analyticsError) {
        addDebugInfo(`Analytics API failed: ${analyticsError.message}`);
        // Don't throw here, as analytics failure shouldn't block performance data
      }

      addDebugInfo("All API calls completed");
    } catch (err) {
      addDebugInfo(`Error in fetchData: ${err.message}`);
      console.error("❌ Fetch Error:", err);
      setError(`Failed to fetch data: ${err.message}`);
    } finally {
      setLoading(false);
      addDebugInfo("Data fetch completed, loading set to false");
    }
  }, [addDebugInfo]);

  const retryFetch = () => {
    addDebugInfo("Manual retry initiated");
    fetchData();
  };

  const clearDebugInfo = () => {
    setDebugInfo([]);
  };

  return (
    <Container maxWidth="xl">
      <Typography variant="h4" gutterBottom>
        Portfolio Performance (Debug Version)
      </Typography>

      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          Authentication Status:
        </Typography>
        <Paper sx={{ p: 2, bgcolor: "grey.50" }}>
          <Typography>
            Auth Loading: {authLoading ? "⏳ Yes" : "✅ No"}
          </Typography>
          <Typography>
            Authenticated: {isAuthenticated ? "✅ Yes" : "❌ No"}
          </Typography>
          <Typography>
            User: {user ? `✅ ${user.username}` : "❌ None"}
          </Typography>
          <Typography>
            Access Token:{" "}
            {localStorage.getItem("accessToken") ? "✅ Present" : "❌ Missing"}
          </Typography>
        </Paper>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
          <Button onClick={retryFetch} sx={{ ml: 2 }}>
            Retry
          </Button>
        </Alert>
      )}

      {(loading || authLoading) && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
          <CircularProgress />
          <Typography>
            {authLoading
              ? "Initializing authentication..."
              : "Loading portfolio data..."}
          </Typography>
        </Box>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Data Status
          </Typography>

          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle1">Performance Data:</Typography>
            {performanceData ? (
              <Typography color="success.main">
                ✅ Loaded ({performanceData?.data?.performance?.length || 0} data
                points)
              </Typography>
            ) : (
              <Typography color="error.main">❌ Not loaded</Typography>
            )}
          </Box>

          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle1">Analytics Data:</Typography>
            {analyticsData ? (
              <Typography color="success.main">
                ✅ Loaded ({analyticsData?.data?.holdings?.length || 0} holdings)
              </Typography>
            ) : (
              <Typography color="error.main">❌ Not loaded</Typography>
            )}
          </Box>

          <Box sx={{ display: "flex", gap: 2 }}>
            <Button onClick={retryFetch} variant="outlined">
              Reload Data
            </Button>
            <Button onClick={clearDebugInfo} variant="outlined">
              Clear Debug Log
            </Button>
          </Box>
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Debug Log ({(debugInfo?.length || 0)} entries):
          </Typography>
          <Box
            sx={{ maxHeight: 400, overflow: "auto", bgcolor: "grey.50", p: 1 }}
          >
            {(debugInfo || []).map((info, index) => (
              <Typography
                key={index}
                variant="body2"
                sx={{
                  fontFamily: "monospace",
                  marginBottom: "2px",
                  fontSize: "0.75rem",
                }}
              >
                {info}
              </Typography>
            ))}
          </Box>
        </CardContent>
      </Card>
    </Container>
  );
};

export default PortfolioPerformanceDebug;
