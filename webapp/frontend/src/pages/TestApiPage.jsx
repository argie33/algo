import React, { useState, useEffect } from "react";
import {
  Container,
  Typography,
  Button,
  Box,
  Alert,
  Card,
  CardContent,
} from "@mui/material";
import {
  getPortfolioPerformance,
  getPortfolioAnalytics,
} from "../services/api";

const TestApiPage = () => {
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const testApi = async () => {
    setLoading(true);
    setError(null);
    const testResults = {};

    try {
      console.log("🧪 Testing API endpoints...");

      // Test portfolio performance
      console.log("Testing getPortfolioPerformance...");
      const perfResult = await getPortfolioPerformance("1Y");
      testResults.performance = {
        success: true,
        data: perfResult,
        dataLength: perfResult?.data?.performance?.length || 0,
      };
      console.log("✅ Portfolio Performance success:", perfResult);

      // Test portfolio analytics
      console.log("Testing getPortfolioAnalytics...");
      const analyticsResult = await getPortfolioAnalytics("1Y");
      testResults.analytics = {
        success: true,
        data: analyticsResult,
        holdingsCount: analyticsResult?.data?.holdings?.length || 0,
      };
      console.log("✅ Portfolio Analytics success:", analyticsResult);
    } catch (err) {
      console.error("❌ API Test failed:", err);
      setError(err.message);
      testResults.error = err.message;
    }

    setResults(testResults);
    setLoading(false);
  };

  useEffect(() => {
    testApi();
  }, []);

  return (
    <Container maxWidth="md">
      <Box sx={{ mt: 4 }}>
        <Typography variant="h4" gutterBottom>
          API Test Page
        </Typography>
        <Typography variant="body1" sx={{ mb: 3 }}>
          This page tests the API endpoints used by the Portfolio Performance
          page.
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            Error: {error}
          </Alert>
        )}

        <Button
          variant="contained"
          onClick={testApi}
          disabled={loading}
          sx={{ mb: 3 }}
        >
          {loading ? "Testing..." : "Test API Endpoints"}
        </Button>

        {Object.keys(results).length > 0 && (
          <Box>
            <Typography variant="h6" gutterBottom>
              Test Results:
            </Typography>

            {results.performance && (
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="h6" color="success.main">
                    ✅ Portfolio Performance API
                  </Typography>
                  <Typography variant="body2">
                    Data points: {results.performance.dataLength}
                  </Typography>
                  <Typography variant="body2">
                    Status: {results.performance.success ? "SUCCESS" : "FAILED"}
                  </Typography>
                </CardContent>
              </Card>
            )}

            {results.analytics && (
              <Card sx={{ mb: 2 }}>
                <CardContent>
                  <Typography variant="h6" color="success.main">
                    ✅ Portfolio Analytics API
                  </Typography>
                  <Typography variant="body2">
                    Holdings count: {results.analytics.holdingsCount}
                  </Typography>
                  <Typography variant="body2">
                    Status: {results.analytics.success ? "SUCCESS" : "FAILED"}
                  </Typography>
                </CardContent>
              </Card>
            )}

            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Raw Results:
                </Typography>
                <Box
                  component="pre"
                  sx={{ fontSize: "0.75rem", overflow: "auto", maxHeight: 300 }}
                >
                  {JSON.stringify(results, null, 2)}
                </Box>
              </CardContent>
            </Card>
          </Box>
        )}
      </Box>
    </Container>
  );
};

export default TestApiPage;
