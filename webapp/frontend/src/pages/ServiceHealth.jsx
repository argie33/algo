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
  const [comprehensiveMode, setComprehensiveMode] = useState(true); // Default to comprehensive view

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
  // Manual database health check state
  const [dbHealth, setDbHealth] = useState(null);
  const [dbLoading, setDbLoading] = useState(false);
  const [dbError, setDbError] = useState(null);
  
  const refetchDb = async () => {
    const startTime = Date.now();
    setDbLoading(true);
    setDbError(null);
    try {
      console.log('Starting enhanced database health check...');
      console.log('Request started at:', new Date().toISOString());
      
      const response = await api.get('/health', {
        timeout: 30000, // Reduced from 3 minutes to 30 seconds
        validateStatus: (status) => status < 500
      });
        
        const endTime = Date.now();
        const duration = endTime - startTime;
        console.log(`Database health check completed in ${duration}ms`);
        
        // Handle case where response has error but is still returned
        if (response.data && response.data.error) {
          console.warn('Database health check returned error:', response.data.error);
          const errorResult = {
            database: {
              status: 'error',
              tables: {},
              summary: { 
                total_tables: 0, 
                healthy_tables: 0, 
                total_records: 0
              },
              error: response.data.error
            },
            message: response.data.error,
            usingFallback: true,
            timestamp: new Date().toISOString()
          };
          setDbHealth(errorResult);
          return errorResult;
        }
        
        setDbHealth(response.data);
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
        
        const result = {
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
        setDbError(error);
        setDbHealth(result);
        return result;
    } finally {
      setDbLoading(false);
    }
  };




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

  // Comprehensive endpoint tests - testing every single route that exists in the backend
  const comprehensiveEndpoints = useMemo(() => [
    {
      category: 'System Health & Debug',
      tests: [
        { name: 'Health Check', fn: () => api.get('/health'), critical: true },
        { name: 'Health Ready', fn: () => api.get('/health/ready'), critical: true },
        { name: 'Health Debug DB', fn: () => api.get('/health/debug/db-test'), critical: false },
        { name: 'Health Debug Tables', fn: () => api.get('/health/debug/tables'), critical: false },
        { name: 'Health Debug Query', fn: () => api.get('/health/debug/test-query'), critical: false },
        { name: 'Health Debug Env', fn: () => api.get('/health/debug/env'), critical: false },
        { name: 'Health Debug CORS', fn: () => api.get('/health/debug/cors-test'), critical: false }
      ]
    },
    {
      category: 'Stock Data & Screening',
      tests: [
        { name: 'Stock List', fn: () => getStocks({ limit: 10 }), critical: true },
        { name: 'Stock Detail (AAPL)', fn: () => api.get('/stocks/AAPL'), critical: true },
        { name: 'Stock Screen', fn: () => screenStocks({ limit: 10 }), critical: true },
        { name: 'Screener Templates', fn: () => api.get('/screener/templates'), critical: false },
        { name: 'Screener Growth', fn: () => api.get('/screener/growth'), critical: false },
        { name: 'Screener Value', fn: () => api.get('/screener/value'), critical: false },
        { name: 'Screener Results', fn: () => api.get('/screener/results'), critical: false }
      ]
    },
    {
      category: 'Technical Analysis',
      tests: [
        { name: 'Technical Daily', fn: () => getTechnicalData('daily', { limit: 10 }), critical: true },
        { name: 'Technical Detail (AAPL)', fn: () => api.get('/technical/AAPL?timeframe=daily'), critical: false },
        { name: 'Technical Root', fn: () => api.get('/technical'), critical: false }
      ]
    },
    {
      category: 'Market Data & Analysis',
      tests: [
        { name: 'Market Overview', fn: () => getMarketOverview(), critical: true },
        { name: 'Market Root', fn: () => api.get('/market'), critical: false },
        { name: 'Market Data Quotes', fn: () => api.get('/market-data/quotes'), critical: false },
        { name: 'Market Data Status', fn: () => api.get('/market-data/status'), critical: false },
        { name: 'Market Data Calendar', fn: () => api.get('/market-data/calendar'), critical: false },
        { name: 'Market Data Assets', fn: () => api.get('/market-data/assets'), critical: false }
      ]
    },
    {
      category: 'Trading & Signals',
      tests: [
        { name: 'Buy Signals Daily', fn: () => getBuySignals(), critical: true },
        { name: 'Sell Signals Daily', fn: () => getSellSignals(), critical: true },
        { name: 'Signals Root', fn: () => api.get('/signals'), critical: false },
        { name: 'Trading Root', fn: () => api.get('/trading'), critical: false }
      ]
    },
    {
      category: 'Portfolio & Holdings',
      tests: [
        { name: 'Portfolio Root', fn: () => api.get('/portfolio'), critical: false },
        { name: 'Portfolio Holdings', fn: () => api.get('/portfolio/holdings'), critical: false },
        { name: 'Trades Root', fn: () => api.get('/trades'), critical: false }
      ]
    },
    {
      category: 'Financial Data',
      tests: [
        { name: 'Financials Root', fn: () => api.get('/financials'), critical: false },
        { name: 'Financials Ping', fn: () => api.get('/financials/ping'), critical: false },
        { name: 'Financials Debug Tables', fn: () => api.get('/financials/debug/tables'), critical: false },
        { name: 'Financials AAPL Balance', fn: () => api.get('/financials/AAPL/balance-sheet'), critical: false },
        { name: 'Financials AAPL Income', fn: () => api.get('/financials/AAPL/income-statement'), critical: false },
        { name: 'Financials AAPL Cash Flow', fn: () => api.get('/financials/AAPL/cash-flow'), critical: false },
        { name: 'Financials AAPL Key Metrics', fn: () => api.get('/financials/AAPL/key-metrics'), critical: false }
      ]
    },
    {
      category: 'Analyst Data',
      tests: [
        { name: 'Analyst Upgrades', fn: () => api.get('/analysts/upgrades'), critical: false },
        { name: 'Analyst Recent Actions', fn: () => api.get('/analysts/recent-actions'), critical: false },
        { name: 'Analyst AAPL Recommendations', fn: () => api.get('/analysts/AAPL/recommendations'), critical: false },
        { name: 'Analyst AAPL Earnings Est', fn: () => api.get('/analysts/AAPL/earnings-estimates'), critical: false },
        { name: 'Analyst AAPL Revenue Est', fn: () => api.get('/analysts/AAPL/revenue-estimates'), critical: false },
        { name: 'Analyst AAPL Overview', fn: () => api.get('/analysts/AAPL/overview'), critical: false }
      ]
    },
    {
      category: 'Metrics & Scoring',
      tests: [
        { name: 'Metrics Root', fn: () => api.get('/metrics'), critical: false },
        { name: 'Metrics Ping', fn: () => api.get('/metrics/ping'), critical: false },
        { name: 'Metrics Dashboard', fn: () => api.get('/metrics/dashboard'), critical: false },
        { name: 'Metrics AAPL Detail', fn: () => api.get('/metrics/AAPL'), critical: false },
        { name: 'Metrics Sectors Analysis', fn: () => api.get('/metrics/sectors/analysis'), critical: false },
        { name: 'Metrics Top Quality', fn: () => api.get('/metrics/top/quality'), critical: false },
        { name: 'Metrics Top Value', fn: () => api.get('/metrics/top/value'), critical: false },
        { name: 'Metrics Top Growth', fn: () => api.get('/metrics/top/growth'), critical: false }
      ]
    },
    {
      category: 'Calendar & Events',
      tests: [
        { name: 'Calendar Root', fn: () => api.get('/calendar'), critical: false },
        { name: 'Calendar Debug', fn: () => api.get('/calendar/debug'), critical: false },
        { name: 'Calendar Test', fn: () => api.get('/calendar/test'), critical: false },
        { name: 'Calendar Events', fn: () => api.get('/calendar/events'), critical: false },
        { name: 'Calendar Summary', fn: () => api.get('/calendar/summary'), critical: false },
        { name: 'Calendar Earnings Est', fn: () => api.get('/calendar/earnings-estimates'), critical: false },
        { name: 'Calendar Earnings History', fn: () => api.get('/calendar/earnings-history'), critical: false }
      ]
    },
    {
      category: 'Data Management',
      tests: [
        { name: 'Data Root', fn: () => api.get('/data'), critical: false },
        { name: 'Data Quality', fn: () => api.get('/data/quality'), critical: false },
        { name: 'Data Sources', fn: () => api.get('/data/sources'), critical: false },
        { name: 'Data EPS Revisions', fn: () => api.get('/data/eps-revisions'), critical: false },
        { name: 'Data EPS Trend', fn: () => api.get('/data/eps-trend'), critical: false },
        { name: 'Data Growth Estimates', fn: () => api.get('/data/growth-estimates'), critical: false },
        { name: 'Data Economic', fn: () => api.get('/data/economic'), critical: false },
        { name: 'Data NAAIM', fn: () => api.get('/data/naaim'), critical: false },
        { name: 'Data Fear Greed', fn: () => api.get('/data/fear-greed'), critical: false },
        { name: 'Data Validation Summary', fn: () => api.get('/data/validation-summary'), critical: false }
      ]
    },
    {
      category: 'Dashboard APIs',
      tests: [
        { name: 'Dashboard Summary', fn: () => api.get('/dashboard/summary'), critical: true },
        { name: 'Dashboard Holdings', fn: () => api.get('/dashboard/holdings'), critical: false },
        { name: 'Dashboard Performance', fn: () => api.get('/dashboard/performance'), critical: false },
        { name: 'Dashboard Alerts', fn: () => api.get('/dashboard/alerts'), critical: false },
        { name: 'Dashboard Market Data', fn: () => api.get('/dashboard/market-data'), critical: false },
        { name: 'Dashboard Debug', fn: () => api.get('/dashboard/debug'), critical: false },
        { name: 'Dashboard Watchlist', fn: () => api.get('/dashboard/watchlist'), critical: false },
        { name: 'Dashboard Symbols', fn: () => api.get('/dashboard/symbols'), critical: false },
        { name: 'Dashboard Market Summary', fn: () => api.get('/dashboard/market-summary'), critical: false },
        { name: 'Dashboard Signals', fn: () => api.get('/dashboard/signals'), critical: false }
      ]
    },
    {
      category: 'Watchlist Management',
      tests: [
        { name: 'Watchlist Root', fn: () => api.get('/watchlist'), critical: false }
      ]
    },
    {
      category: 'Sector Analysis',
      tests: [
        { name: 'Sectors Root', fn: () => api.get('/sectors'), critical: false },
        { name: 'Sectors Analysis', fn: () => api.get('/sectors/analysis'), critical: false }
      ]
    },
    {
      category: 'Pattern Recognition',
      tests: [
        { name: 'Patterns Root', fn: () => api.get('/patterns'), critical: false },
        { name: 'Patterns Scan', fn: () => api.get('/patterns/scan'), critical: false },
        { name: 'Patterns Types', fn: () => api.get('/patterns/types'), critical: false },
        { name: 'Patterns Performance', fn: () => api.get('/patterns/performance'), critical: false },
        { name: 'Patterns Alerts', fn: () => api.get('/patterns/alerts'), critical: false },
        { name: 'Patterns Dashboard', fn: () => api.get('/patterns/dashboard'), critical: false },
        { name: 'Patterns Statistics', fn: () => api.get('/patterns/statistics'), critical: false }
      ]
    },
    {
      category: 'Backtesting',
      tests: [
        { name: 'Backtest Strategies', fn: () => api.get('/backtest/strategies'), critical: false },
        { name: 'Backtest Symbols', fn: () => api.get('/backtest/symbols'), critical: false },
        { name: 'Backtest Templates', fn: () => api.get('/backtest/templates'), critical: false },
        { name: 'Backtest History', fn: () => api.get('/backtest/history'), critical: false }
      ]
    },
    {
      category: 'Cryptocurrency',
      tests: [
        { name: 'Crypto Market Metrics', fn: () => api.get('/crypto/market-metrics'), critical: false },
        { name: 'Crypto Fear Greed', fn: () => api.get('/crypto/fear-greed'), critical: false },
        { name: 'Crypto Movers', fn: () => api.get('/crypto/movers'), critical: false },
        { name: 'Crypto Trending', fn: () => api.get('/crypto/trending'), critical: false },
        { name: 'Crypto Assets', fn: () => api.get('/crypto/assets'), critical: false },
        { name: 'Crypto DeFi TVL', fn: () => api.get('/crypto/defi/tvl'), critical: false },
        { name: 'Crypto Exchanges', fn: () => api.get('/crypto/exchanges'), critical: false }
      ]
    },
    {
      category: 'News & Sentiment',
      tests: [
        { name: 'News Articles', fn: () => api.get('/news/articles'), critical: false },
        { name: 'News Market Sentiment', fn: () => api.get('/news/market-sentiment'), critical: false },
        { name: 'News Sources', fn: () => api.get('/news/sources'), critical: false },
        { name: 'News Categories', fn: () => api.get('/news/categories'), critical: false },
        { name: 'News Trending', fn: () => api.get('/news/trending'), critical: false }
      ]
    },
    {
      category: 'Economic Data',
      tests: [
        { name: 'Economic Indicators', fn: () => api.get('/economic/indicators'), critical: false },
        { name: 'Economic Calendar', fn: () => api.get('/economic/calendar'), critical: false },
        { name: 'Economic Models', fn: () => api.get('/economic/models'), critical: false },
        { name: 'Economic Correlations', fn: () => api.get('/economic/correlations'), critical: false },
        { name: 'Economic Forecasts', fn: () => api.get('/economic/forecasts'), critical: false },
        { name: 'Economic Yield Curve', fn: () => api.get('/economic/yield-curve'), critical: false },
        { name: 'Economic Inflation', fn: () => api.get('/economic/inflation'), critical: false },
        { name: 'Economic Employment', fn: () => api.get('/economic/employment'), critical: false },
        { name: 'Economic GDP', fn: () => api.get('/economic/gdp'), critical: false },
        { name: 'Economic Indicators List', fn: () => api.get('/economic/indicators/list'), critical: false }
      ]
    },
    {
      category: 'Commodities',
      tests: [
        { name: 'Commodities Categories', fn: () => api.get('/commodities/categories'), critical: false },
        { name: 'Commodities Prices', fn: () => api.get('/commodities/prices'), critical: false },
        { name: 'Commodities Market Summary', fn: () => api.get('/commodities/market-summary'), critical: false },
        { name: 'Commodities Correlations', fn: () => api.get('/commodities/correlations'), critical: false },
        { name: 'Commodities News', fn: () => api.get('/commodities/news'), critical: false }
      ]
    },
    {
      category: 'AI Assistant',
      tests: [
        { name: 'AI History', fn: () => api.get('/ai-assistant/history'), critical: false },
        { name: 'AI Config', fn: () => api.get('/ai-assistant/config'), critical: false },
        { name: 'AI Market Context', fn: () => api.get('/ai-assistant/market-context'), critical: false }
      ]
    },
    {
      category: 'Alerts & Notifications',
      tests: [
        { name: 'Alerts Root', fn: () => api.get('/alerts'), critical: false },
        { name: 'Alerts Notifications', fn: () => api.get('/alerts/notifications'), critical: false },
        { name: 'Alerts Types', fn: () => api.get('/alerts/types'), critical: false }
      ]
    },
    {
      category: 'User Settings',
      tests: [
        { name: 'Settings Root', fn: () => api.get('/settings'), critical: false }
      ]
    },
    {
      category: 'External Data Sources',
      tests: [
        { name: 'NAAIM Data', fn: () => getNaaimData({ limit: 5 }), critical: false },
        { name: 'Fear & Greed Data', fn: () => getFearGreedData({ limit: 5 }), critical: false }
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

  // Manual health check state
  const [healthData, setHealthData] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState(null);
  
  const refetchHealth = async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const result = await healthCheck();
      setHealthData(result);
      return result;
    } catch (error) {
      console.error('Health check failed:', error);
      setHealthError(error);
      throw error;
    } finally {
      setHealthLoading(false);
    }
  };

  // Auto-run API tests on component mount
  useEffect(() => {
    // Run API tests automatically when component mounts
    testAllEndpoints();
  }, [testAllEndpoints]);

  // Refresh health status background job
  const refreshHealthStatus = async () => {
    try {
      setRefreshing(true);
      console.log('🔄 Triggering comprehensive database health update...');
      
      // Call the backend to update health status
      const response = await api.post('/health/update-status', {}, {
        timeout: 60000 // 1 minute timeout for comprehensive analysis
      });
      
      console.log('✅ Health status update completed:', response.data.message);
      
      // Refetch the health data to show updated results
      await refetchDb();
      
    } catch (error) {
      console.error('❌ Failed to refresh health status:', error);
      // Don't throw - just log the error so UI doesn't break
    } finally {
      setRefreshing(false);
    }
  };
  
  // Note: health_status table creation is handled by db-init, not runtime

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
              <Box sx={{ ml: 'auto', display: 'flex', gap: 1 }}>
                <Button 
                  variant="outlined" 
                  size="small" 
                  startIcon={<Refresh />}
                  onClick={refreshHealthStatus}
                  disabled={refreshing}
                >
                  {refreshing ? 'Updating...' : 'Update All Tables'}
                </Button>
              </Box>
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
