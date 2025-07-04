import React, { useState, useEffect } from 'react';
import { Container, Typography, CircularProgress, Alert, Card, CardContent, Button } from '@mui/material';
import { getPortfolioPerformance, getPortfolioAnalytics } from '../services/api';

const PortfolioPerformanceSimple = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [performanceData, setPerformanceData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [debugInfo, setDebugInfo] = useState([]);

  const addDebugInfo = (message) => {
    console.log('🐛 DEBUG:', message);
    setDebugInfo(prev => [...prev, `${new Date().toLocaleTimeString()}: ${message}`]);
  };

  useEffect(() => {
    addDebugInfo('Component mounted, starting data fetch...');
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      addDebugInfo('Setting loading to true, clearing error');

      // Test 1: Portfolio Performance
      addDebugInfo('Calling getPortfolioPerformance...');
      const perfResponse = await getPortfolioPerformance('1Y');
      addDebugInfo(`Performance API response: ${JSON.stringify(perfResponse, null, 2).substring(0, 200)}...`);
      setPerformanceData(perfResponse);

      // Test 2: Portfolio Analytics
      addDebugInfo('Calling getPortfolioAnalytics...');
      const analyticsResponse = await getPortfolioAnalytics('1Y');
      addDebugInfo(`Analytics API response: ${JSON.stringify(analyticsResponse, null, 2).substring(0, 200)}...`);
      setAnalyticsData(analyticsResponse);

      addDebugInfo('All API calls completed successfully');
    } catch (err) {
      addDebugInfo(`Error occurred: ${err.message}`);
      console.error('❌ API Error:', err);
      setError(`Failed to fetch data: ${err.message}`);
    } finally {
      setLoading(false);
      addDebugInfo('Setting loading to false');
    }
  };

  const retryFetch = () => {
    addDebugInfo('Manual retry initiated');
    fetchData();
  };

  if (loading) {
    return (
      <Container maxWidth="md">
        <Typography variant="h4" gutterBottom>
          Portfolio Performance (Simple Debug Version)
        </Typography>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
          <CircularProgress />
          <Typography>Loading portfolio data...</Typography>
        </div>
        <Card>
          <CardContent>
            <Typography variant="h6">Debug Information:</Typography>
            {debugInfo.map((info, index) => (
              <Typography key={index} variant="body2" style={{ fontFamily: 'monospace', marginBottom: '4px' }}>
                {info}
              </Typography>
            ))}
          </CardContent>
        </Card>
      </Container>
    );
  }

  return (
    <Container maxWidth="md">
      <Typography variant="h4" gutterBottom>
        Portfolio Performance (Simple Debug Version)
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
          <Button onClick={retryFetch} sx={{ ml: 2 }}>
            Retry
          </Button>
        </Alert>
      )}

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Performance Data Status
          </Typography>
          {performanceData ? (
            <div>
              <Typography color="success.main">✅ Performance data loaded successfully</Typography>
              <Typography>
                Data points: {performanceData.data?.performance?.length || 0}
              </Typography>
              <Typography>
                Success: {performanceData.success ? 'true' : 'false'}
              </Typography>
            </div>
          ) : (
            <Typography color="error.main">❌ No performance data</Typography>
          )}
        </CardContent>
      </Card>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Analytics Data Status
          </Typography>
          {analyticsData ? (
            <div>
              <Typography color="success.main">✅ Analytics data loaded successfully</Typography>
              <Typography>
                Holdings: {analyticsData.data?.holdings?.length || 0}
              </Typography>
              <Typography>
                Success: {analyticsData.success ? 'true' : 'false'}
              </Typography>
            </div>
          ) : (
            <Typography color="error.main">❌ No analytics data</Typography>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Debug Information:
          </Typography>
          {debugInfo.map((info, index) => (
            <Typography key={index} variant="body2" style={{ fontFamily: 'monospace', marginBottom: '4px' }}>
              {info}
            </Typography>
          ))}
          <Button onClick={retryFetch} variant="outlined" sx={{ mt: 2 }}>
            Reload Data
          </Button>
        </CardContent>
      </Card>
    </Container>
  );
};

export default PortfolioPerformanceSimple;