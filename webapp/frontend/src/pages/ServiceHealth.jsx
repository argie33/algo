import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { 
  Box,
  Container,
  Typography, 
  Grid, 
  Card,
  CardContent,
  Alert,
  CircularProgress,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  Button,
  IconButton,
  Tooltip
} from '@mui/material';
import { 
  ExpandMore,
  CheckCircle, 
  Error, 
  Warning, 
  Info,
  Refresh,
  Storage,
  Api,
  Cloud,
  ToggleOff,
  ToggleOn
} from '@mui/icons-material';

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
  api
} from '../services/api';

function isObject(val) {
  return val && typeof val === 'object' && !Array.isArray(val);
}

function ServiceHealth() {
  const [environmentInfo, setEnvironmentInfo] = useState({});
  const [testResults, setTestResults] = useState({});
  const [testingInProgress, setTestingInProgress] = useState(false);
  const [componentError, setComponentError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [comprehensiveMode, setComprehensiveMode] = useState(false);

  // Memoize diagnosticInfo to prevent infinite re-renders
  const diagnosticInfo = useMemo(() => {
    try {
      return getDiagnosticInfo();
    } catch (error) {
      console.error('Error getting diagnostic info:', error);
      return {};
    }
  }, []);
  
  // Memoize other API config calls to prevent infinite re-renders
  const apiConfig = useMemo(() => {
    try {
      return getApiConfig();
    } catch (error) {
      console.error('Error getting API config:', error);
      return {};
    }
  }, []);
  const currentBaseURL = useMemo(() => {
    try {
      return getCurrentBaseURL();
    } catch (error) {
      console.error('Error getting current base URL:', error);
      return '';
    }
  }, []);

  // Component error handler
  useEffect(() => {
    const handleError = (event) => {
      console.error('ServiceHealth component error:', event.error);
      setComponentError(event.error.message);
    };
    
    window.addEventListener('error', handleError);
    return () => window.removeEventListener('error', handleError);
  }, []);

  // Enhanced comprehensive health checks
  const { data: dbHealth, isLoading: dbLoading, error: dbError, refetch: refetchDb } = useQuery({
    queryKey: ['databaseHealth'],
    queryFn: async () => {
      const startTime = Date.now();
      try {
        console.log('Starting enhanced database health check...');
        console.log('Request started at:', new Date().toISOString());
        
        const response = await api.get('/health', {
          timeout: 180000, // 3 minutes
          validateStatus: (status) => status < 500
        });
        
        const endTime = Date.now();
        const duration = endTime - startTime;
        console.log(`Database health check completed in ${duration}ms`);
        
        return response.data;
      } catch (error) {
        const endTime = Date.now();
        const duration = endTime - startTime;
        
        console.error('Database health check failed:', error);
        console.error('Request duration before failure:', duration + 'ms');
        console.error('Error details:', {
          message: error.message,
          code: error.code,
          status: error.response?.status,
          statusText: error.response?.statusText,
          timeout: error.code === 'ECONNABORTED',
          networkError: !error.response
        });
        
        // Determine likely cause of timeout
        let timeoutCause = 'Unknown';
        if (error.code === 'ECONNABORTED' && duration >= 179000) {
          timeoutCause = 'Request timeout (3 min) - likely slow database query';
        } else if (error.code === 'ECONNABORTED' && duration < 30000) {
          timeoutCause = 'Early timeout - likely connection issue';
        } else if (!error.response && error.code !== 'ECONNABORTED') {
          timeoutCause = 'Network error - cannot reach server';
        } else if (error.response?.status >= 500) {
          timeoutCause = 'Server error - backend issue';
        }
        
        return {
          error: true,
          message: error.message || 'Unknown database health error',
          timeoutCause: timeoutCause,
          requestDuration: duration,
          errorCode: error.code,
          httpStatus: error.response?.status,
          timestamp: new Date().toISOString(),
          database: { 
            status: 'error',
            tables: {},
            summary: { 
              total_tables: 0, 
              healthy_tables: 0, 
              total_records: 0
            }
          }
        };
      }
    },
    refetchInterval: 120000, // Auto-refresh every 2 minutes (less frequent due to longer timeout)
    retry: 1,
    staleTime: 60000,
    enabled: true
  });




  // Early return if component has error
  if (componentError) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="error">
          <Typography variant="h6">Service Health Error</Typography>
          <Typography variant="body2">
            {componentError}
          </Typography>
          <Button onClick={() => window.location.reload()} sx={{ mt: 2 }}>
            Reload Page
          </Button>
        </Alert>
      </Container>
    );
  }

  // Simplified endpoint tests - only test essential endpoints
  const quickEndpoints = useMemo(() => [
    { name: 'Health Check', fn: () => healthCheck(), critical: true },
    { name: 'API Connection', fn: () => testApiConnection(), critical: true },
    { name: 'Stocks', fn: () => getStocks({ limit: 5 }), critical: true },
    { name: 'Technical Data', fn: () => getTechnicalData('daily', { limit: 5 }), critical: true },
    { name: 'Market Overview', fn: () => getMarketOverview(), critical: true },
    { name: 'Stock Screener', fn: () => screenStocks({ limit: 5 }), critical: false },
    { name: 'Buy Signals', fn: () => getBuySignals(), critical: false },
    { name: 'Sell Signals', fn: () => getSellSignals(), critical: false },
    { name: 'NAAIM Data', fn: () => getNaaimData({ limit: 5 }), critical: false },
    { name: 'Fear & Greed', fn: () => getFearGreedData({ limit: 5 }), critical: false }
  ], []);

  // Comprehensive endpoint tests - organized by category
  const comprehensiveEndpoints = useMemo(() => [
    {
      category: 'System Health',
      tests: [
        { name: 'Health Check (Quick)', fn: () => healthCheck('?quick=true'), critical: true },
        { name: 'Health Check (Full)', fn: () => healthCheck(), critical: true },
        { name: 'Database Health', fn: () => api.get('/health'), critical: true },
        { name: 'Table Readiness Check', fn: () => api.get('/health/ready'), critical: false },
        { name: 'Quick Health Check', fn: () => api.get('/health?quick=true'), critical: false }
      ]
    },
    {
      category: 'Stock Data',
      tests: [
        { name: 'Stock List', fn: () => getStocks({ limit: 10 }), critical: true },
        { name: 'Stock Detail (AAPL)', fn: () => api.get('/stocks/AAPL'), critical: true },
        { name: 'Stock Screen', fn: () => screenStocks({ limit: 10 }), critical: true },
        { name: 'Stock Search', fn: () => api.get('/stocks/search?q=AAPL'), critical: false },
        { name: 'Stock Prices (AAPL)', fn: () => api.get('/stocks/AAPL/prices'), critical: false }
      ]
    },
    {
      category: 'Technical Analysis',
      tests: [
        { name: 'Technical Daily', fn: () => getTechnicalData('daily', { limit: 10 }), critical: true },
        { name: 'Technical Weekly', fn: () => getTechnicalData('weekly', { limit: 10 }), critical: false },
        { name: 'Technical Monthly', fn: () => getTechnicalData('monthly', { limit: 10 }), critical: false },
        { name: 'Technical Detail (AAPL)', fn: () => api.get('/technical/AAPL'), critical: false }
      ]
    },
    {
      category: 'Market Data',
      tests: [
        { name: 'Market Overview', fn: () => getMarketOverview(), critical: true },
        { name: 'Market Summary', fn: () => api.get('/market/summary'), critical: true },
        { name: 'Market Indices', fn: () => api.get('/market/indices'), critical: false },
        { name: 'Market Breadth', fn: () => api.get('/market/breadth'), critical: false },
        { name: 'Sector Performance', fn: () => api.get('/market/sectors'), critical: false }
      ]
    },
    {
      category: 'Trading & Signals',
      tests: [
        { name: 'Buy Signals Daily', fn: () => getBuySignals(), critical: true },
        { name: 'Sell Signals Daily', fn: () => getSellSignals(), critical: true },
        { name: 'Buy Signals Weekly', fn: () => api.get('/trading/signals/weekly'), critical: false },
        { name: 'Buy Signals Monthly', fn: () => api.get('/trading/signals/monthly'), critical: false },
        { name: 'Signals Summary', fn: () => api.get('/signals/summary'), critical: false }
      ]
    },
    {
      category: 'Financial Data',
      tests: [
        { name: 'Financials (AAPL)', fn: () => api.get('/financials/AAPL'), critical: false },
        { name: 'Income Statement (AAPL)', fn: () => api.get('/financials/AAPL/income'), critical: false },
        { name: 'Balance Sheet (AAPL)', fn: () => api.get('/financials/AAPL/balance'), critical: false },
        { name: 'Cash Flow (AAPL)', fn: () => api.get('/financials/AAPL/cashflow'), critical: false },
        { name: 'Key Metrics (AAPL)', fn: () => api.get('/financials/AAPL/metrics'), critical: false }
      ]
    },
    {
      category: 'Metrics & Scoring',
      tests: [
        { name: 'Metrics List', fn: () => api.get('/metrics'), critical: false },
        { name: 'Metrics Detail (AAPL)', fn: () => api.get('/metrics/AAPL'), critical: false },
        { name: 'Top Quality Stocks', fn: () => api.get('/metrics/top/quality'), critical: false },
        { name: 'Top Value Stocks', fn: () => api.get('/metrics/top/value'), critical: false },
        { name: 'Top Composite Stocks', fn: () => api.get('/metrics/top/composite'), critical: false }
      ]
    },
    {
      category: 'Calendar & Events',
      tests: [
        { name: 'Earnings Calendar', fn: () => api.get('/calendar/earnings'), critical: false },
        { name: 'Economic Calendar', fn: () => api.get('/calendar/economic'), critical: false },
        { name: 'Calendar Events', fn: () => api.get('/calendar'), critical: false }
      ]
    },
    {
      category: 'Portfolio',
      tests: [
        { name: 'Portfolio Overview', fn: () => api.get('/portfolio'), critical: false },
        { name: 'Portfolio Holdings', fn: () => api.get('/portfolio/holdings'), critical: false },
        { name: 'Portfolio Performance', fn: () => api.get('/portfolio/performance'), critical: false },
        { name: 'Portfolio Analytics', fn: () => api.get('/portfolio/analytics'), critical: false }
      ]
    },
    {
      category: 'Dashboard APIs',
      tests: [
        { name: 'Dashboard Summary', fn: () => api.get('/dashboard/summary'), critical: true },
        { name: 'Market Summary', fn: () => api.get('/dashboard/market-summary'), critical: false },
        { name: 'Watchlist', fn: () => api.get('/dashboard/watchlist'), critical: false },
        { name: 'Dashboard Signals', fn: () => api.get('/dashboard/signals'), critical: false },
        { name: 'Dashboard Symbols', fn: () => api.get('/dashboard/symbols'), critical: false }
      ]
    },
    {
      category: 'Data Management',
      tests: [
        { name: 'Data Status', fn: () => api.get('/data'), critical: false },
        { name: 'Data Sources', fn: () => api.get('/data/sources'), critical: false },
        { name: 'Data Quality', fn: () => api.get('/data/quality'), critical: false }
      ]
    },
    {
      category: 'External Data',
      tests: [
        { name: 'NAAIM Data', fn: () => getNaaimData({ limit: 5 }), critical: false },
        { name: 'Fear & Greed', fn: () => getFearGreedData({ limit: 5 }), critical: false }
      ]
    },
    {
      category: 'Authentication & Security',
      tests: [
        { name: 'Auth Status', fn: () => api.get('/auth/status'), critical: true },
        { name: 'Token Validation', fn: () => api.get('/auth/validate'), critical: true },
        { name: 'User Profile', fn: () => api.get('/auth/profile'), critical: false }
      ]
    },
    {
      category: 'Settings & Configuration',
      tests: [
        { name: 'User Settings', fn: () => api.get('/settings'), critical: false },
        { name: 'API Keys List', fn: () => api.get('/settings/api-keys'), critical: false },
        { name: 'Trading Preferences', fn: () => api.get('/settings/trading'), critical: false },
        { name: 'Notification Settings', fn: () => api.get('/settings/notifications'), critical: false }
      ]
    },
    {
      category: 'Trading & Execution',
      tests: [
        { name: 'Trade History', fn: () => api.get('/trades/history'), critical: false },
        { name: 'Open Orders', fn: () => api.get('/trades/orders'), critical: false },
        { name: 'Trade Summary', fn: () => api.get('/trades/summary'), critical: false },
        { name: 'Position Summary', fn: () => api.get('/trades/positions'), critical: false }
      ]
    },
    {
      category: 'Cryptocurrency',
      tests: [
        { name: 'Crypto Overview', fn: () => api.get('/crypto'), critical: false },
        { name: 'Crypto Prices (BTC)', fn: () => api.get('/crypto/BTC/price'), critical: false },
        { name: 'Crypto Market Data', fn: () => api.get('/crypto/market'), critical: false },
        { name: 'Top Cryptocurrencies', fn: () => api.get('/crypto/top'), critical: false }
      ]
    },
    {
      category: 'Stock Screening',
      tests: [
        { name: 'Screener Templates', fn: () => api.get('/screener/templates'), critical: false },
        { name: 'Growth Stocks Screen', fn: () => api.get('/screener/growth'), critical: false },
        { name: 'Value Stocks Screen', fn: () => api.get('/screener/value'), critical: false },
        { name: 'Custom Screen Results', fn: () => api.get('/screener/results'), critical: false }
      ]
    },
    {
      category: 'Technical Patterns',
      tests: [
        { name: 'Pattern Overview', fn: () => api.get('/patterns'), critical: false },
        { name: 'Bullish Patterns', fn: () => api.get('/patterns/bullish'), critical: false },
        { name: 'Bearish Patterns', fn: () => api.get('/patterns/bearish'), critical: false },
        { name: 'Pattern Alerts', fn: () => api.get('/patterns/alerts'), critical: false }
      ]
    },
    {
      category: 'Watchlists',
      tests: [
        { name: 'All Watchlists', fn: () => api.get('/watchlist'), critical: false },
        { name: 'Default Watchlist', fn: () => api.get('/watchlist/default'), critical: false },
        { name: 'Watchlist Analytics', fn: () => api.get('/watchlist/analytics'), critical: false },
        { name: 'Watchlist Performance', fn: () => api.get('/watchlist/performance'), critical: false }
      ]
    },
    {
      category: 'Sector Analysis',
      tests: [
        { name: 'Sector Overview', fn: () => api.get('/sectors'), critical: false },
        { name: 'Sector Performance', fn: () => api.get('/sectors/performance'), critical: false },
        { name: 'Sector Rotation', fn: () => api.get('/sectors/rotation'), critical: false },
        { name: 'Technology Sector', fn: () => api.get('/sectors/technology'), critical: false }
      ]
    },
    {
      category: 'Backtesting',
      tests: [
        { name: 'Backtest Results', fn: () => api.get('/backtest/results'), critical: false },
        { name: 'Strategy Performance', fn: () => api.get('/backtest/strategies'), critical: false },
        { name: 'Backtest History', fn: () => api.get('/backtest/history'), critical: false },
        { name: 'Risk Metrics', fn: () => api.get('/backtest/risk'), critical: false }
      ]
    },
    {
      category: 'AI Assistant',
      tests: [
        { name: 'AI Status', fn: () => api.get('/ai/status'), critical: false },
        { name: 'AI Chat History', fn: () => api.get('/ai/chat/history'), critical: false },
        { name: 'AI Recommendations', fn: () => api.get('/ai/recommendations'), critical: false },
        { name: 'AI Analysis Summary', fn: () => api.get('/ai/analysis'), critical: false }
      ]
    },
    {
      category: 'Real-time Pricing',
      tests: [
        { name: 'Price Quotes (AAPL)', fn: () => api.get('/price/AAPL'), critical: false },
        { name: 'Real-time Feed Status', fn: () => api.get('/price/status'), critical: false },
        { name: 'Price Alerts', fn: () => api.get('/price/alerts'), critical: false },
        { name: 'Market Hours', fn: () => api.get('/price/market-hours'), critical: false }
      ]
    }
  ], []);

  const endpoints = comprehensiveMode ? comprehensiveEndpoints : quickEndpoints;

  // Test all endpoints
  const testAllEndpoints = useCallback(async () => {
    setTestingInProgress(true);
    const results = {};
    
    if (comprehensiveMode) {
      // Test comprehensive endpoints by category
      for (const category of endpoints) {
        results[category.category] = {};
        for (const endpoint of category.tests) {
          const startTime = Date.now();
          try {
            console.log(`Testing endpoint: ${category.category} - ${endpoint.name}`);
            const response = await endpoint.fn();
            const responseTime = Date.now() - startTime;
            
            results[category.category][endpoint.name] = {
              status: 'success',
              responseTime: responseTime,
              critical: endpoint.critical,
              data: response?.data || response,
              error: null
            };
          } catch (error) {
            const responseTime = Date.now() - startTime;
            console.error(`Endpoint ${endpoint.name} failed:`, error);
            
            results[category.category][endpoint.name] = {
              status: 'error',
              responseTime: responseTime,
              critical: endpoint.critical,
              data: null,
              error: error.message || 'Unknown error',
              details: error.response?.data || error.response?.status || 'No additional details'
            };
          }
        }
      }
    } else {
      // Test quick endpoints
      for (const endpoint of endpoints) {
        const startTime = Date.now();
        try {
          console.log(`Testing endpoint: ${endpoint.name}`);
          const response = await endpoint.fn();
          const responseTime = Date.now() - startTime;
          
          results[endpoint.name] = {
            status: 'success',
            responseTime: responseTime,
            critical: endpoint.critical,
            data: response?.data || response,
            error: null
          };
        } catch (error) {
          const responseTime = Date.now() - startTime;
          console.error(`Endpoint ${endpoint.name} failed:`, error);
          
          results[endpoint.name] = {
            status: 'error',
            responseTime: responseTime,
            critical: endpoint.critical,
            data: null,
            error: error.message || 'Unknown error',
            details: error.response?.data || error.response?.status || 'No additional details'
          };
        }
      }
    }
    setTestResults(results);
    setTestingInProgress(false);
  }, [endpoints, comprehensiveMode]);

  // Health check query - simplified
  const { data: healthData, isLoading: healthLoading, error: healthError, refetch: refetchHealth } = useQuery({
    queryKey: ['serviceHealth'],
    queryFn: async () => {
      try {
        const result = await healthCheck();
        return result;
      } catch (error) {
        console.error('Health check failed:', error);
        throw error;
      }
    },
    refetchInterval: false,
    retry: 1,
    staleTime: 30000,
    enabled: true // Auto-run on mount
  });

  // Auto-run API tests on component mount
  useEffect(() => {
    // Run API tests automatically when component mounts
    testAllEndpoints();
  }, [testAllEndpoints]);

  // Refresh health status background job
  const refreshHealthStatus = async () => {
    try {
      setRefreshing(true);
      
      // Use the standard api instance to trigger background update
      // Note: Health status update not implemented yet
      console.log('Health status would be updated here');
      
      // Use React Query's refetch to get updated data
      await refetchDb();
      
    } catch (error) {
      console.error('Failed to refresh health status:', error);
      // Don't throw - just log the error
    } finally {
      setRefreshing(false);
    }
  };

  // Gather environment information
  useEffect(() => {
    const env = {
      Frontend: {
        ...apiConfig,
        location: window.location.href,
        userAgent: navigator.userAgent.substring(0, 100) + '...',
        timestamp: new Date().toISOString(),
        viteApiUrl: 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
        currentBaseURL: currentBaseURL,
        diagnosticInfo: diagnosticInfo
      }
    };
    setEnvironmentInfo(env);
  }, [apiConfig, diagnosticInfo, currentBaseURL]);

  // Safe data extraction
  const safeHealthData = isObject(healthData) ? healthData : {};
  const safeDbHealth = isObject(dbHealth) ? dbHealth : {};
  const safeTestResults = isObject(testResults) ? testResults : {};
  const safeEnvironmentInfo = isObject(environmentInfo) ? environmentInfo : {};
  const safeDiagnosticInfo = isObject(diagnosticInfo) ? diagnosticInfo : {};

  const getStatusIcon = (status) => {
    switch (status) {
      case 'success':
      case 'healthy':
      case 'connected':
        return <CheckCircle color="success" />;
      case 'error':
      case 'failed':
      case 'disconnected':
        return <Error color="error" />;
      case 'warning':
      case 'stale':
      case 'incomplete':
        return <Warning color="warning" />;
      case 'empty':
        return <Info color="info" />;
      default:
        return <Info color="info" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'success':
      case 'healthy':
      case 'connected':
        return 'success';
      case 'error':
      case 'failed':
      case 'disconnected':
        return 'error';
      case 'warning':
      case 'stale':
      case 'incomplete':
        return 'warning';
      case 'empty':
        return 'info';
      default:
        return 'default';
    }
  };

  const formatNumber = (num) => {
    if (num === null || num === undefined) return 'N/A';
    return new Intl.NumberFormat().format(num);
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
  };

  const formatTimeAgo = (dateString) => {
    if (!dateString) return 'N/A';
    const now = new Date();
    const date = new Date(dateString);
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffDays > 0) {
      return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    } else if (diffHours > 0) {
      return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    } else {
      const diffMinutes = Math.floor(diffMs / (1000 * 60));
      return `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`;
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
            <CardContent sx={{ textAlign: 'center' }}>
              {healthLoading ? (
                <CircularProgress />
              ) : healthError ? (
                <>
                  <Error color="error" sx={{ fontSize: 40, mb: 1 }} />
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
                {refreshing ? 'Refreshing...' : 'Refresh Health Status'}
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Api sx={{ fontSize: 40, mb: 1, color: 'primary.main' }} />
              <Typography variant="h6">
                API Gateway
              </Typography>
              <Typography variant="body2" color="textSecondary">
                {safeDiagnosticInfo?.isConfigured ? 'Configured' : 'Not Configured'}
              </Typography>
              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                {safeDiagnosticInfo?.urlsMatch ? 'URLs Match' : 'URL Mismatch'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Storage sx={{ fontSize: 40, mb: 1, color: 'primary.main' }} />
              <Typography variant="h6">
                Database
              </Typography>
              <Typography variant="body2" color="textSecondary">
                {dbLoading ? 'Checking...' : 
                 dbError ? 'Error' : 
                 safeDbHealth?.database?.status === 'connected' ? 'Connected' :
                 safeDbHealth?.database?.status === 'disconnected' ? 'Disconnected' : 
                 safeDbHealth?.error ? 'Error' :
                 'Unknown'}
              </Typography>
              {dbError && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  <Typography variant="subtitle2">Failed to load database health:</Typography>
                  <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                    {typeof dbError === 'string' ? dbError : dbError?.message || 'Unknown error'}
                  </Typography>
                </Alert>
              )}
              {safeDbHealth?.error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  <Typography variant="subtitle2">Database Error:</Typography>
                  <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                    {safeDbHealth.message || 'Unknown error'}
                  </Typography>
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Cloud sx={{ fontSize: 40, mb: 1, color: 'primary.main' }} />
              <Typography variant="h6">
                Environment
              </Typography>
              <Typography variant="body2" color="textSecondary">
                {(() => {
                  const env = import.meta.env.VITE_ENV || import.meta.env.MODE || '';
                  if (env.toLowerCase().startsWith('prod')) return 'Production';
                  if (env.toLowerCase().startsWith('stag')) return 'Staging';
                  if (env.toLowerCase().startsWith('dev')) return 'Development';
                  if (env) return env.charAt(0).toUpperCase() + env.slice(1);
                  return 'Production';
                })()}
              </Typography>
                      <Typography variant="caption" display="block" sx={{ mt: 1 }} title={'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev'}>
          API: https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>


      {/* Detailed Health Information */}
      <Grid container spacing={3}>
        {/* API Health */}
        <Grid item xs={12} lg={6}>
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography variant="h6">
                <Api sx={{ mr: 1, verticalAlign: 'middle' }} />
                API Health
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              {safeHealthData && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Status: {safeHealthData.status}
                  </Typography>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    Last Updated: {new Date(safeHealthData.timestamp).toLocaleString()}
                  </Typography>
                  
                  {safeHealthData.api && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2">API Information:</Typography>
                      <Typography variant="body2">Version: {safeHealthData.api.version}</Typography>
                      <Typography variant="body2">Environment: {safeHealthData.api.environment}</Typography>
                    </Box>
                  )}
                </Box>
              )}
              
              <Box sx={{ mt: 2, display: 'flex', gap: 2, alignItems: 'center' }}>
                <Button
                  variant="outlined" 
                  size="small" 
                  startIcon={<Refresh />}
                  onClick={testAllEndpoints}
                  disabled={testingInProgress}
                >
                  {testingInProgress ? 'Testing...' : 'Test All Endpoints'}
                </Button>
                <Tooltip title={comprehensiveMode ? 'Switch to quick mode for faster testing' : 'Switch to comprehensive mode for thorough testing'}>
                  <Button
                    variant="text"
                    size="small"
                    startIcon={comprehensiveMode ? <ToggleOn /> : <ToggleOff />}
                    onClick={() => setComprehensiveMode(!comprehensiveMode)}
                    disabled={testingInProgress}
                  >
                    {comprehensiveMode ? 'Comprehensive Mode' : 'Quick Mode'}
                  </Button>
                </Tooltip>
              </Box>

              {Object.keys(safeTestResults).length > 0 && (
                <Box sx={{ mt: 2 }}>
                  {comprehensiveMode ? (
                    // Comprehensive mode: Display by category
                    Object.entries(safeTestResults).map(([category, tests]) => (
                      <Accordion key={category} defaultExpanded>
                        <AccordionSummary expandIcon={<ExpandMore />}>
                          <Typography variant="subtitle1">{category}</Typography>
                          <Box sx={{ ml: 'auto', mr: 2 }}>
                            {(() => {
                              const testArray = Object.values(tests || {});
                              const successCount = testArray.filter(t => t && t.status === 'success').length;
                              const totalCount = testArray.length;
                              const allSuccess = successCount === totalCount;
                              return (
                                <Chip
                                  label={`${successCount}/${totalCount}`}
                                  color={allSuccess ? 'success' : 'warning'}
                                  size="small"
                                />
                              );
                            })()}
                          </Box>
                        </AccordionSummary>
                        <AccordionDetails>
                          <TableContainer component={Paper}>
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell>Endpoint</TableCell>
                                  <TableCell>Status</TableCell>
                                  <TableCell>Response Time</TableCell>
                                  <TableCell>Critical</TableCell>
                                  <TableCell>Error</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {Object.entries(tests || {}).map(([name, result]) => (
                                  <TableRow key={name}>
                                    <TableCell>{name}</TableCell>
                                    <TableCell>
                                      <Chip
                                        icon={getStatusIcon(result?.status)}
                                        label={result?.status || 'Unknown'}
                                        color={getStatusColor(result?.status)}
                                        size="small"
                                      />
                                    </TableCell>
                                    <TableCell>
                                      {result?.responseTime ? `${result.responseTime}ms` : '-'}
                                    </TableCell>
                                    <TableCell>
                                      {result?.critical && (
                                        <Chip label="Critical" size="small" variant="outlined" />
                                      )}
                                    </TableCell>
                                    <TableCell>
                                      {result?.error ? (
                                        <Tooltip title={result.details || result.error}>
                                          <Typography variant="body2" sx={{ 
                                            maxWidth: 300, 
                                            overflow: 'hidden', 
                                            textOverflow: 'ellipsis',
                                            cursor: 'help'
                                          }}>
                                            {result.error}
                                          </Typography>
                                        </Tooltip>
                                      ) : '-'}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </TableContainer>
                        </AccordionDetails>
                      </Accordion>
                    ))
                  ) : (
                    // Quick mode: Simple table
                    <TableContainer component={Paper}>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Endpoint</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell>Response Time</TableCell>
                            <TableCell>Critical</TableCell>
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
                                  label={result?.status || 'Unknown'}
                                  color={getStatusColor(result?.status)}
                                  size="small"
                                />
                              </TableCell>
                              <TableCell>
                                {result?.responseTime ? `${result.responseTime}ms` : '-'}
                              </TableCell>
                              <TableCell>
                                {result?.critical && (
                                  <Chip label="Critical" size="small" variant="outlined" />
                                )}
                              </TableCell>
                              <TableCell>
                                {result?.error || '-'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )}
                </Box>
              )}
            </AccordionDetails>
          </Accordion>
        </Grid>

        {/* Database Health */}
        <Grid item xs={12} lg={6}>
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography variant="h6">
                <Storage sx={{ mr: 1, verticalAlign: 'middle' }} />
                Database Health
              </Typography>
              <Button 
                variant="outlined" 
                size="small" 
                startIcon={<Refresh />}
                onClick={refreshHealthStatus}
                sx={{ ml: 'auto', mr: 2 }}
                disabled={refreshing}
              >
                {refreshing ? 'Updating...' : 'Update All Tables'}
              </Button>
            </AccordionSummary>
            <AccordionDetails>
              {dbLoading && (
                <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                  <CircularProgress size={24} />
                  <Typography sx={{ ml: 2 }}>Loading database health...</Typography>
                </Box>
              )}
              
              {dbError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <Typography variant="subtitle2">Failed to load database health:</Typography>
                  <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                    {typeof dbError === 'string' ? dbError : dbError?.message || 'Unknown error'}
                  </Typography>
                </Alert>
              )}

              {safeDbHealth && (
                <Box>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>Database Status:</Typography>
                    <Typography variant="body2">Status: {safeDbHealth.database?.status || 'Unknown'}</Typography>
                    {safeDbHealth.database?.currentTime && (
                      <Typography variant="body2">Current Time: {new Date(safeDbHealth.database.currentTime).toLocaleString()}</Typography>
                    )}
                    {safeDbHealth.database?.postgresVersion && (
                      <Typography variant="body2">PostgreSQL Version: {safeDbHealth.database.postgresVersion}</Typography>
                    )}
                  </Box>

                  {/* Backend error/message display */}
                  {safeDbHealth.error || safeDbHealth.message || safeDbHealth.details ? (
                    <Alert severity="error" sx={{ mb: 2 }}>
                      <Typography variant="subtitle2">Backend Error:</Typography>
                      {safeDbHealth.error && (
                        <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Error:</b> {safeDbHealth.error}
                        </Typography>
                      )}
                      {safeDbHealth.message && (
                        <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Message:</b> {safeDbHealth.message}
                        </Typography>
                      )}
                      {safeDbHealth.timeoutCause && (
                        <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Likely Cause:</b> {safeDbHealth.timeoutCause}
                        </Typography>
                      )}
                      {safeDbHealth.requestDuration && (
                        <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Request Duration:</b> {Math.round(safeDbHealth.requestDuration / 1000)}s
                        </Typography>
                      )}
                      {safeDbHealth.errorCode && (
                        <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Error Code:</b> {safeDbHealth.errorCode}
                        </Typography>
                      )}
                      {safeDbHealth.httpStatus && (
                        <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>HTTP Status:</b> {safeDbHealth.httpStatus}
                        </Typography>
                      )}
                      {safeDbHealth.details && (
                        <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Details:</b> {safeDbHealth.details}
                        </Typography>
                      )}
                    </Alert>
                  ) : null}

                  {/* Summary Statistics */}
                  {safeDbHealth.database?.summary && (
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Summary:</Typography>
                      <Grid container spacing={1}>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="text.secondary">
                            Total Tables: {safeDbHealth.database.summary.total_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="success.main">
                            Healthy: {safeDbHealth.database.summary.healthy_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="warning.main">
                            Stale: {safeDbHealth.database.summary.stale_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="error.main">
                            Errors: {safeDbHealth.database.summary.error_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="info.main">
                            Empty: {safeDbHealth.database.summary.empty_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="text.secondary">
                            Missing: {safeDbHealth.database.summary.missing_tables}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="text.secondary">
                            Total Records: {formatNumber(safeDbHealth.database.summary.total_records)}
                          </Typography>
                        </Grid>
                        <Grid item xs={6} sm={3}>
                          <Typography variant="body2" color="warning.main">
                            Missing Data: {formatNumber(safeDbHealth.database.summary.total_missing_data)}
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>
                  )}

                  {/* Detailed Table List */}
                  {safeDbHealth.database?.tables && Object.keys(safeDbHealth.database.tables).length > 0 && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>
                        Table Details ({Object.keys(safeDbHealth.database.tables).length} tables monitored):
                      </Typography>
                      <TableContainer component={Paper} sx={{ maxHeight: 600 }}>
                        <Table size="small" stickyHeader>
                          <TableHead>
                            <TableRow>
                              <TableCell>Table</TableCell>
                              <TableCell>Category</TableCell>
                              <TableCell align="right">Records</TableCell>
                              <TableCell>Status</TableCell>
                              <TableCell>Critical</TableCell>
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
                              <TableRow key={tableName} sx={{ 
                                backgroundColor: tableData.critical_table ? 'rgba(25, 118, 210, 0.04)' : 'inherit',
                                '&:hover': { backgroundColor: 'rgba(0, 0, 0, 0.04)' }
                              }}>
                                <TableCell component="th" scope="row">
                                  <Box>
                                    <Typography variant="body2" fontFamily="monospace" fontWeight={600}>
                                      {tableName}
                                    </Typography>
                                    {tableData.table_category && (
                                      <Typography variant="caption" color="text.secondary">
                                        {tableData.table_category}
                                      </Typography>
                                    )}
                                  </Box>
                                </TableCell>
                                <TableCell>
                                  {tableData.table_category && (
                                    <Chip
                                      label={tableData.table_category}
                                      size="small"
                                      variant="outlined"
                                      sx={{ 
                                        fontSize: '0.7rem',
                                        height: 20,
                                        backgroundColor: 
                                          tableData.table_category === 'symbols' ? '#e3f2fd' :
                                          tableData.table_category === 'prices' ? '#f3e5f5' :
                                          tableData.table_category === 'technicals' ? '#e8f5e8' :
                                          tableData.table_category === 'financials' ? '#fff3e0' :
                                          tableData.table_category === 'company' ? '#e0f2f1' :
                                          tableData.table_category === 'earnings' ? '#fce4ec' :
                                          tableData.table_category === 'sentiment' ? '#f1f8e9' :
                                          tableData.table_category === 'trading' ? '#e8eaf6' :
                                          '#f5f5f5'
                                      }}
                                    />
                                  )}
                                </TableCell>
                                <TableCell align="right">
                                  <Typography variant="body2" fontWeight={600}>
                                    {formatNumber(tableData.record_count)}
                                  </Typography>
                                </TableCell>
                                <TableCell>
                                  <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
                                    <Chip
                                      icon={getStatusIcon(tableData?.status)}
                                      label={tableData?.status || 'Unknown'}
                                      color={getStatusColor(tableData?.status)}
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
                                  {tableData.critical_table && (
                                    <Chip
                                      label="Critical"
                                      color="error"
                                      size="small"
                                      variant="outlined"
                                    />
                                  )}
                                </TableCell>
                                <TableCell>
                                  <Box>
                                    <Typography variant="body2">
                                      {formatDate(tableData.last_updated)}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                      {formatTimeAgo(tableData.last_updated)}
                                    </Typography>
                                  </Box>
                                </TableCell>
                                <TableCell align="right">
                                  {tableData.missing_data_count > 0 ? (
                                    <Typography variant="body2" color="warning.main" fontWeight={600}>
                                      {formatNumber(tableData.missing_data_count)}
                                    </Typography>
                                  ) : (
                                    <Typography variant="body2" color="success.main">
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
                                      <Typography variant="body2" color="error" sx={{ 
                                        maxWidth: 200, 
                                        overflow: 'hidden', 
                                        textOverflow: 'ellipsis',
                                        cursor: 'help'
                                      }}>
                                        {tableData.error.length > 30 ? `${tableData.error.substring(0, 30)}...` : tableData.error}
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
                  {(!safeDbHealth.database?.tables || Object.keys(safeDbHealth.database.tables).length === 0) && (
                    <Alert severity="warning" sx={{ mt: 2 }}>
                      <Typography variant="subtitle2">No table data found</Typography>
                      <Typography variant="body2">
                        The database health check did not return any table information. 
                        This could mean the health_status table is empty or the backend is not properly configured.
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

        {/* Environment Information */}
        <Grid item xs={12} lg={6}>
          <Accordion>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography variant="h6">
                <Info sx={{ mr: 1, verticalAlign: 'middle' }} />
                Environment Information
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              {Object.keys(safeEnvironmentInfo).length > 0 && (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableBody>
                      {Object.entries(safeEnvironmentInfo).map(([section, values]) => (
                        <React.Fragment key={section}>
                          <TableRow>
                            <TableCell colSpan={2} sx={{ fontWeight: 'bold', backgroundColor: 'grey.100' }}>
                              {section}
                            </TableCell>
                          </TableRow>
                          {isObject(values) && Object.entries(values).map(([key, value]) => (
                            <TableRow key={`${section}-${key}`}>
                              <TableCell component="th" scope="row" sx={{ fontWeight: 'bold', pl: 3 }}>
                                {key}
                              </TableCell>
                              <TableCell>
                                <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                                  {String(value ?? 'undefined')}
                                </Typography>
                              </TableCell>
                            </TableRow>
                          ))}
                        </React.Fragment>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </AccordionDetails>
          </Accordion>
        </Grid>

        {/* API Configuration Diagnostics */}
        <Grid item xs={12} lg={6}>
          <Accordion>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography variant="h6">
                <Api sx={{ mr: 1, verticalAlign: 'middle' }} />
                API Configuration Diagnostics
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              {Object.keys(safeDiagnosticInfo).length > 0 && (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          Current API URL
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {safeDiagnosticInfo.currentApiUrl || 'Not set'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          Axios Default Base URL
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {safeDiagnosticInfo.axiosDefaultBaseUrl || 'Not set'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          VITE_API_URL
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {safeDiagnosticInfo.viteApiUrl || 'Not set'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          URLs Match
                        </TableCell>
                        <TableCell>
                          <Chip
                            icon={getStatusIcon(safeDiagnosticInfo.urlsMatch ? 'success' : 'error')}
                            label={safeDiagnosticInfo.urlsMatch ? 'Yes' : 'No'}
                            color={getStatusColor(safeDiagnosticInfo.urlsMatch ? 'success' : 'error')}
                            size="small"
                          />
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          Is Configured
                        </TableCell>
                        <TableCell>
                          <Chip
                            icon={getStatusIcon(safeDiagnosticInfo.isConfigured ? 'success' : 'error')}
                            label={safeDiagnosticInfo.isConfigured ? 'Yes' : 'No'}
                            color={getStatusColor(safeDiagnosticInfo.isConfigured ? 'success' : 'error')}
                            size="small"
                          />
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </AccordionDetails>
          </Accordion>
        </Grid>

      </Grid>
    </Container>
  );
}

export default ServiceHealth;
