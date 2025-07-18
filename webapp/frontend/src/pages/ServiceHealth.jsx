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

// Import components
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

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
        
        console.log('✅ Database health data received: [REDACTED]');
        console.log('📊 Database status:', response.data.database?.status);
        console.log('📋 Tables found:', Object.keys(response.data.database?.tables || {}).length);
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

  // Run database health check on component mount
  useEffect(() => {
    refetchDb();
  }, []);

  // Early return if component has error
  if (componentError) {
    return (
      <div className="container mx-auto" maxWidth="lg" sx={{ py: 4 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">
          <div  variant="h6">Service Health Error</div>
          <div  variant="body2">
            {componentError}
          </div>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => window.location.reload()} sx={{ mt: 2 }}>
            Reload Page
          </button>
        </div>
      </div>
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

  // Removed auto-run API tests on component mount per user request
  // API tests now only run when button is pressed manually
  // useEffect(() => {
  //   // Run API tests automatically when component mounts
  //   testAllEndpoints();
  // }, [testAllEndpoints]);

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
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 3 }}>
      <div  sx={{ mb: 3 }}>
        <div  variant="h4" component="h1" gutterBottom>
          Service Health Dashboard
        </div>
        <div  variant="subtitle1" color="textSecondary">
          Monitor system status, API health, and data integrity
        </div>
      </div>

      {/* API Key Status Integration */}
      <div  sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          showSetupDialog={true}
          onStatusChange={(status) => {
            console.log('Service Health - API Key Status:', status);
          }}
        />
      </div>

      {/* Overall Status */}
      <div className="grid" container spacing={3} sx={{ mb: 3 }}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
              {healthLoading ? (
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
              ) : healthError ? (
                <>
                  <Error color="error" sx={{ fontSize: 40, mb: 1 }} />
                  <div  variant="h6" color="error">
                    Service Down
                  </div>
                </>
              ) : (
                <>
                  <CheckCircle color="success" sx={{ fontSize: 40, mb: 1 }} />
                  <div  variant="h6" color="success.main">
                    Service Healthy
                  </div>
                </>
              )}
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="outlined" 
                size="small" 
                startIcon={<Refresh />}
                onClick={refetchHealth}
                sx={{ mt: 1 }}
                disabled={refreshing}
              >
                {refreshing ? 'Refreshing...' : 'Refresh Health Status'}
              </button>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
              <Api sx={{ fontSize: 40, mb: 1, color: 'primary.main' }} />
              <div  variant="h6">
                API Gateway
              </div>
              <div  variant="body2" color="textSecondary">
                {safeDiagnosticInfo?.isConfigured ? 'Configured' : 'Not Configured'}
              </div>
              <div  variant="caption" display="block" sx={{ mt: 1 }}>
                {safeDiagnosticInfo?.urlsMatch ? 'URLs Match' : 'URL Mismatch'}
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
              <Storage sx={{ fontSize: 40, mb: 1, color: 'primary.main' }} />
              <div  variant="h6">
                Database
              </div>
              <div  variant="body2" color="textSecondary">
                {dbLoading ? 'Checking...' : 
                 dbError ? 'Error' : 
                 safeDbHealth?.database?.status === 'connected' ? 'Connected' :
                 safeDbHealth?.database?.status === 'disconnected' ? 'Disconnected' : 
                 safeDbHealth?.status === 'healthy' ? 'Healthy' :
                 safeDbHealth?.error ? 'Error' :
                 dbHealth === null ? 'Not checked' :
                 'Unknown'}
              </div>
              {dbError && (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mt: 2 }}>
                  <div  variant="subtitle2">Failed to load database health:</div>
                  <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                    {typeof dbError === 'string' ? dbError : dbError?.message || 'Unknown error'}
                  </div>
                </div>
              )}
              {safeDbHealth?.error && (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mt: 2 }}>
                  <div  variant="subtitle2">Database Error:</div>
                  <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                    {safeDbHealth.message || 'Unknown error'}
                  </div>
                </div>
              )}
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="outlined" 
                size="small" 
                startIcon={<Refresh />}
                onClick={refetchDb}
                sx={{ mt: 1 }}
                disabled={dbLoading}
              >
                {dbLoading ? 'Checking...' : 'Check Database'}
              </button>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
              <Cloud sx={{ fontSize: 40, mb: 1, color: 'primary.main' }} />
              <div  variant="h6">
                Environment
              </div>
              <div  variant="body2" color="textSecondary">
                {(() => {
                  const env = import.meta.env.VITE_ENV || import.meta.env.MODE || '';
                  if (env.toLowerCase().startsWith('prod')) return 'Production';
                  if (env.toLowerCase().startsWith('stag')) return 'Staging';
                  if (env.toLowerCase().startsWith('dev')) return 'Development';
                  if (env) return env.charAt(0).toUpperCase() + env.slice(1);
                  return 'Production';
                })()}
              </div>
                      <div  variant="caption" display="block" sx={{ mt: 1 }} title={'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev'}>
          API: https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev
              </div>
            </div>
          </div>
        </div>
      </div>


      {/* Detailed Health Information */}
      <div className="grid" container spacing={3}>
        {/* API Health */}
        <div className="grid" item xs={12} lg={6}>
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <div  variant="h6">
                <Api sx={{ mr: 1, verticalAlign: 'middle' }} />
                API Health
              </div>
            </AccordionSummary>
            <AccordionDetails>
              {safeHealthData && (
                <div>
                  <div  variant="subtitle2" gutterBottom>
                    Status: {safeHealthData.status}
                  </div>
                  <div  variant="body2" color="textSecondary" gutterBottom>
                    Last Updated: {new Date(safeHealthData.timestamp).toLocaleString()}
                  </div>
                  
                  {safeHealthData.api && (
                    <div  sx={{ mt: 2 }}>
                      <div  variant="subtitle2">API Information:</div>
                      <div  variant="body2">Version: {safeHealthData.api.version}</div>
                      <div  variant="body2">Environment: {safeHealthData.api.environment}</div>
                    </div>
                  )}
                </div>
              )}
              
              <div  sx={{ mt: 2, display: 'flex', gap: 2, alignItems: 'center' }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined" 
                  size="small" 
                  startIcon={<Refresh />}
                  onClick={testAllEndpoints}
                  disabled={testingInProgress}
                >
                  {testingInProgress ? 'Testing...' : 'Test All Endpoints'}
                </button>
                <div  title={comprehensiveMode ? 'Switch to quick mode for faster testing' : 'Switch to comprehensive mode for thorough testing'}>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="text"
                    size="small"
                    startIcon={comprehensiveMode ? <ToggleOn /> : <ToggleOff />}
                    onClick={() => setComprehensiveMode(!comprehensiveMode)}
                    disabled={testingInProgress}
                  >
                    {comprehensiveMode ? 'Comprehensive Mode' : 'Quick Mode'}
                  </button>
                </div>
              </div>

              {Object.keys(safeTestResults).length > 0 && (
                <div  sx={{ mt: 2 }}>
                  {comprehensiveMode ? (
                    // Comprehensive mode: Display by category
                    Object.entries(safeTestResults).map(([category, tests]) => (
                      <Accordion key={category} defaultExpanded>
                        <AccordionSummary expandIcon={<ExpandMore />}>
                          <div  variant="subtitle1">{category}</div>
                          <div  sx={{ ml: 'auto', mr: 2 }}>
                            {(() => {
                              const testArray = Object.values(tests || {});
                              const successCount = testArray.filter(t => t && t.status === 'success').length;
                              const totalCount = testArray.length;
                              const allSuccess = successCount === totalCount;
                              return (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                  label={`${successCount}/${totalCount}`}
                                  color={allSuccess ? 'success' : 'warning'}
                                  size="small"
                                />
                              );
                            })()}
                          </div>
                        </AccordionSummary>
                        <AccordionDetails>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper}>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Endpoint</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Response Time</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Critical</td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Error</td>
                                </tr>
                              </thead>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                                {Object.entries(tests || {}).map(([name, result]) => (
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={name}>
                                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{name}</td>
                                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                        icon={getStatusIcon(result?.status)}
                                        label={result?.status || 'Unknown'}
                                        color={getStatusColor(result?.status)}
                                        size="small"
                                      />
                                    </td>
                                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                      {result?.responseTime ? `${result.responseTime}ms` : '-'}
                                    </td>
                                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                      {result?.critical && (
                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Critical" size="small" variant="outlined" />
                                      )}
                                    </td>
                                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                      {result?.error ? (
                                        <div  title={result.details || result.error}>
                                          <div  variant="body2" sx={{ 
                                            maxWidth: 300, 
                                            overflow: 'hidden', 
                                            textOverflow: 'ellipsis',
                                            cursor: 'help'
                                          }}>
                                            {result.error}
                                          </div>
                                        </div>
                                      ) : '-'}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </AccordionDetails>
                      </Accordion>
                    ))
                  ) : (
                    // Quick mode: Simple table
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Endpoint</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Response Time</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Critical</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Error</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {Object.entries(safeTestResults).map(([name, result]) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={name}>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{name}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                  icon={getStatusIcon(result?.status)}
                                  label={result?.status || 'Unknown'}
                                  color={getStatusColor(result?.status)}
                                  size="small"
                                />
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                {result?.responseTime ? `${result.responseTime}ms` : '-'}
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                {result?.critical && (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Critical" size="small" variant="outlined" />
                                )}
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                {result?.error || '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </AccordionDetails>
          </Accordion>
        </div>

        {/* Database Health */}
        <div className="grid" item xs={12} lg={6}>
          <Accordion defaultExpanded>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <div  variant="h6">
                <Storage sx={{ mr: 1, verticalAlign: 'middle' }} />
                Database Health
              </div>
              <div  sx={{ ml: 'auto', display: 'flex', gap: 1 }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  size="small" 
                  startIcon={<Refresh />}
                  onClick={refreshHealthStatus}
                  disabled={refreshing}
                >
                  {refreshing ? 'Updating...' : 'Update All Tables'}
                </button>
              </div>
            </AccordionSummary>
            <AccordionDetails>
              {/* Debug info */}
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 2 }}>
                <div  variant="body2">
                  Debug: dbHealth={!!dbHealth ? 'exists' : 'null'}, 
                  safeDbHealth={!!safeDbHealth ? 'exists' : 'empty'}, 
                  dbLoading={dbLoading.toString()}, 
                  dbError={!!dbError ? 'exists' : 'null'}
                </div>
                {safeDbHealth && (
                  <div  variant="body2" sx={{ mt: 1 }}>
                    Data keys: {Object.keys(safeDbHealth).join(', ')}
                  </div>
                )}
              </div>
              
              {dbLoading && (
                <div  sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={24} />
                  <div  sx={{ ml: 2 }}>Loading database health...</div>
                </div>
              )}
              
              {dbError && (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
                  <div  variant="subtitle2">Failed to load database health:</div>
                  <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                    {typeof dbError === 'string' ? dbError : dbError?.message || 'Unknown error'}
                  </div>
                </div>
              )}

              {safeDbHealth && (
                <div>
                  {console.log('🔍 Rendering safeDbHealth:', safeDbHealth)}
                  <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="success" sx={{ mb: 2 }}>
                    <div  variant="subtitle2" gutterBottom>
                      🗄️ Database Status: {safeDbHealth.database?.status === 'connected' ? 'Connected & Healthy' : safeDbHealth.database?.status || 'Unknown'}
                    </div>
                    {safeDbHealth.database?.currentTime && (
                      <div  variant="body2">📅 Server Time: {new Date(safeDbHealth.database.currentTime).toLocaleString()}</div>
                    )}
                    {safeDbHealth.database?.postgresVersion && (
                      <div  variant="body2">⚙️ PostgreSQL: {safeDbHealth.database.postgresVersion}</div>
                    )}
                    {safeDbHealth.database?.note && (
                      <div  variant="body2">📋 {safeDbHealth.database.note}</div>
                    )}
                  </div>

                  {/* Backend error/message display */}
                  {safeDbHealth.error || safeDbHealth.message || safeDbHealth.details ? (
                    <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
                      <div  variant="subtitle2">Backend Error:</div>
                      {safeDbHealth.error && (
                        <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Error:</b> {safeDbHealth.error}
                        </div>
                      )}
                      {safeDbHealth.message && (
                        <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Message:</b> {safeDbHealth.message}
                        </div>
                      )}
                      {safeDbHealth.timeoutCause && (
                        <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Likely Cause:</b> {safeDbHealth.timeoutCause}
                        </div>
                      )}
                      {safeDbHealth.requestDuration && (
                        <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Request Duration:</b> {Math.round(safeDbHealth.requestDuration / 1000)}s
                        </div>
                      )}
                      {safeDbHealth.errorCode && (
                        <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Error Code:</b> {safeDbHealth.errorCode}
                        </div>
                      )}
                      {safeDbHealth.httpStatus && (
                        <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>HTTP Status:</b> {safeDbHealth.httpStatus}
                        </div>
                      )}
                      {safeDbHealth.details && (
                        <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                          <b>Details:</b> {safeDbHealth.details}
                        </div>
                      )}
                    </div>
                  ) : null}

                  {/* Summary Statistics */}
                  {safeDbHealth.database?.summary && (
                    <div className="bg-white shadow-md rounded-lg" sx={{ mb: 2, bgcolor: 'grey.50' }}>
                      <div className="bg-white shadow-md rounded-lg"Content sx={{ py: 2 }}>
                        <div  variant="subtitle2" gutterBottom>📊 Database Tables Summary:</div>
                        <div className="grid" container spacing={1}>
                        <div className="grid" item xs={6} sm={3}>
                          <div  variant="body2" color="text.secondary">
                            Total Tables: {safeDbHealth.database.summary.total_tables}
                          </div>
                        </div>
                        <div className="grid" item xs={6} sm={3}>
                          <div  variant="body2" color="success.main">
                            Healthy: {safeDbHealth.database.summary.healthy_tables}
                          </div>
                        </div>
                        <div className="grid" item xs={6} sm={3}>
                          <div  variant="body2" color="warning.main">
                            Stale: {safeDbHealth.database.summary.stale_tables}
                          </div>
                        </div>
                        <div className="grid" item xs={6} sm={3}>
                          <div  variant="body2" color="error.main">
                            Errors: {safeDbHealth.database.summary.error_tables}
                          </div>
                        </div>
                        <div className="grid" item xs={6} sm={3}>
                          <div  variant="body2" color="info.main">
                            Empty: {safeDbHealth.database.summary.empty_tables}
                          </div>
                        </div>
                        <div className="grid" item xs={6} sm={3}>
                          <div  variant="body2" color="text.secondary">
                            Missing: {safeDbHealth.database.summary.missing_tables}
                          </div>
                        </div>
                        <div className="grid" item xs={6} sm={3}>
                          <div  variant="body2" color="text.secondary">
                            Total Records: {formatNumber(safeDbHealth.database.summary.total_records)}
                          </div>
                        </div>
                        <div className="grid" item xs={6} sm={3}>
                          <div  variant="body2" color="warning.main">
                            Missing Data: {formatNumber(safeDbHealth.database.summary.total_missing_data)}
                          </div>
                        </div>
                      </div>
                      </div>
                    </div>
                  )}

                  {/* Detailed Table List */}
                  {safeDbHealth.database?.tables && Object.keys(safeDbHealth.database.tables).length > 0 && (
                    <div  sx={{ mt: 2 }}>
                      <div  variant="subtitle2" gutterBottom>
                        Table Details ({Object.keys(safeDbHealth.database.tables).length} tables monitored):
                      </div>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} sx={{ maxHeight: 600 }}>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small" stickyHeader>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Table</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Category</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Records</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Critical</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Last Updated</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Missing Data</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Last Checked</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Error</td>
                            </tr>
                          </thead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                            {Object.entries(safeDbHealth.database.tables)
                              .sort(([a], [b]) => a.localeCompare(b))
                              .map(([tableName, tableData]) => (
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={tableName} sx={{ 
                                backgroundColor: tableData.critical_table ? 'rgba(25, 118, 210, 0.04)' : 'inherit',
                                '&:hover': { backgroundColor: 'rgba(0, 0, 0, 0.04)' }
                              }}>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row">
                                  <div>
                                    <div  variant="body2" fontFamily="monospace" fontWeight={600}>
                                      {tableName}
                                    </div>
                                    {tableData.table_category && (
                                      <div  variant="caption" color="text.secondary">
                                        {tableData.table_category}
                                      </div>
                                    )}
                                  </div>
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                  {tableData.table_category && (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
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
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  <div  variant="body2" fontWeight={600}>
                                    {formatNumber(tableData.record_count)}
                                  </div>
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                  <div  sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                      icon={getStatusIcon(tableData?.status)}
                                      label={tableData?.status || 'Unknown'}
                                      color={getStatusColor(tableData?.status)}
                                      size="small"
                                      sx={{ minWidth: 80 }}
                                    />
                                    {tableData.is_stale && (
                                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                        label="Stale"
                                        color="warning"
                                        size="small"
                                      />
                                    )}
                                  </div>
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                  {tableData.critical_table && (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                      label="Critical"
                                      color="error"
                                      size="small"
                                      variant="outlined"
                                    />
                                  )}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                  <div>
                                    <div  variant="body2">
                                      {formatDate(tableData.last_updated)}
                                    </div>
                                    <div  variant="caption" color="text.secondary">
                                      {formatTimeAgo(tableData.last_updated)}
                                    </div>
                                  </div>
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  {tableData.missing_data_count > 0 ? (
                                    <div  variant="body2" color="warning.main" fontWeight={600}>
                                      {formatNumber(tableData.missing_data_count)}
                                    </div>
                                  ) : (
                                    <div  variant="body2" color="success.main">
                                      0
                                    </div>
                                  )}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                  <div  variant="body2">
                                    {formatDate(tableData.last_checked)}
                                  </div>
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                  {tableData.error && (
                                    <div  title={tableData.error}>
                                      <div  variant="body2" color="error" sx={{ 
                                        maxWidth: 200, 
                                        overflow: 'hidden', 
                                        textOverflow: 'ellipsis',
                                        cursor: 'help'
                                      }}>
                                        {tableData.error.length > 30 ? `${tableData.error.substring(0, 30)}...` : tableData.error}
                                      </div>
                                    </div>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Show if no tables found */}
                  {(!safeDbHealth.database?.tables || Object.keys(safeDbHealth.database.tables).length === 0) && (
                    <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" sx={{ mt: 2 }}>
                      <div  variant="subtitle2">No table data found</div>
                      <div  variant="body2">
                        The database health check did not return any table information. 
                        This could mean the health_status table is empty or the backend is not properly configured.
                      </div>
                    </div>
                  )}

                  {safeDbHealth.database?.note && (
                    <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mt: 2 }}>
                      {safeDbHealth.database.note}
                    </div>
                  )}
                </div>
              )}
            </AccordionDetails>
          </Accordion>
        </div>

        {/* Environment Information */}
        <div className="grid" item xs={12} lg={6}>
          <Accordion>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <div  variant="h6">
                <Info sx={{ mr: 1, verticalAlign: 'middle' }} />
                Environment Information
              </div>
            </AccordionSummary>
            <AccordionDetails>
              {Object.keys(safeEnvironmentInfo).length > 0 && (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {Object.entries(safeEnvironmentInfo).map(([section, values]) => (
                        <React.Fragment key={section}>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell colSpan={2} sx={{ fontWeight: 'bold', backgroundColor: 'grey.100' }}>
                              {section}
                            </td>
                          </tr>
                          {isObject(values) && Object.entries(values).map(([key, value]) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={`${section}-${key}`}>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row" sx={{ fontWeight: 'bold', pl: 3 }}>
                                {key}
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                                  {String(value ?? 'undefined')}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </AccordionDetails>
          </Accordion>
        </div>

        {/* API Configuration Diagnostics */}
        <div className="grid" item xs={12} lg={6}>
          <Accordion>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <div  variant="h6">
                <Api sx={{ mr: 1, verticalAlign: 'middle' }} />
                API Configuration Diagnostics
              </div>
            </AccordionSummary>
            <AccordionDetails>
              {Object.keys(safeDiagnosticInfo).length > 0 && (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          Current API URL
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {safeDiagnosticInfo.currentApiUrl || 'Not set'}
                          </div>
                        </td>
                      </tr>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          Axios Default Base URL
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {safeDiagnosticInfo.axiosDefaultBaseUrl || 'Not set'}
                          </div>
                        </td>
                      </tr>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          VITE_API_URL
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {safeDiagnosticInfo.viteApiUrl || 'Not set'}
                          </div>
                        </td>
                      </tr>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          URLs Match
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            icon={getStatusIcon(safeDiagnosticInfo.urlsMatch ? 'success' : 'error')}
                            label={safeDiagnosticInfo.urlsMatch ? 'Yes' : 'No'}
                            color={getStatusColor(safeDiagnosticInfo.urlsMatch ? 'success' : 'error')}
                            size="small"
                          />
                        </td>
                      </tr>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          Is Configured
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            icon={getStatusIcon(safeDiagnosticInfo.isConfigured ? 'success' : 'error')}
                            label={safeDiagnosticInfo.isConfigured ? 'Yes' : 'No'}
                            color={getStatusColor(safeDiagnosticInfo.isConfigured ? 'success' : 'error')}
                            size="small"
                          />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </AccordionDetails>
          </Accordion>
        </div>

      </div>
    </div>
  );
}

export default ServiceHealth;
