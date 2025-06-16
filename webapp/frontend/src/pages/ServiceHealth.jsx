import React, { useState, useEffect } from 'react';
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
  Button,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tabs,
  Tab,
  Divider,
  LinearProgress,
  Badge,
  Tooltip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Switch,
  FormControlLabel
} from '@mui/material';
import {
  ExpandMore,
  HealthAndSafety,
  Storage,
  Api,
  BugReport,
  CheckCircle,
  Error,
  Warning,
  Info,
  Refresh,
  Speed,
  Memory,
  CloudQueue,
  Timeline,
  Analytics,
  NetworkCheck,
  Security,
  Schedule,
  Visibility,
  PlayArrow,
  Stop,
  Download,
  Share
} from '@mui/icons-material';
import { 
  healthCheck, 
  getDataValidationSummary,
  getTechnicalData,
  getStocks,
  getMarketOverview,
  testApiConnection
} from '../services/api';

function ServiceHealth() {
  const [selectedTab, setSelectedTab] = useState(0);
  const [testEndpoint, setTestEndpoint] = useState('');
  const [manualTestResult, setManualTestResult] = useState(null);
  const [endpointTests, setEndpointTests] = useState({});
  const [performanceMetrics, setPerformanceMetrics] = useState({});
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(30000);
  const [logViewOpen, setLogViewOpen] = useState(false);
  const [realTimeLogs, setRealTimeLogs] = useState([]);
  const [networkMetrics, setNetworkMetrics] = useState(null);
  const [securityChecks, setSecurityChecks] = useState({});

  // Enhanced endpoint testing
  const endpoints = [
    { name: 'Health', path: '/health', critical: true },
    { name: 'Stocks', path: '/stocks?limit=5', critical: true },
    { name: 'Technical Daily', path: '/technical/daily?limit=5', critical: true },
    { name: 'Technical Weekly', path: '/technical/weekly?limit=5', critical: false },
    { name: 'Technical Monthly', path: '/technical/monthly?limit=5', critical: false },
    { name: 'Market Overview', path: '/market/overview', critical: true },
    { name: 'Market Sentiment', path: '/market/sentiment/history?days=7', critical: false },
    { name: 'Data Validation', path: '/data/validation-summary', critical: true },
    { name: 'Financial AAPL BS', path: '/financials/AAPL/balance-sheet', critical: false },
    { name: 'Financial AAPL IS', path: '/financials/AAPL/income-statement', critical: false },
    { name: 'Financial AAPL CF', path: '/financials/AAPL/cash-flow', critical: false },
    { name: 'Stock Screener', path: '/stocks?market_cap_min=1000000000&limit=10', critical: true },
    { name: 'Trading Signals', path: '/trading/buy-signals?limit=5', critical: false },
    { name: 'Earnings Estimates', path: '/earnings/estimates?limit=5', critical: false },
    { name: 'Analyst Recs', path: '/analysts/recommendations?limit=5', critical: false }
  ];

  // Environment info gathering
  const environmentInfo = {
    VITE_API_URL: import.meta.env.VITE_API_URL,
    MODE: import.meta.env.MODE,
    DEV: import.meta.env.DEV,
    PROD: import.meta.env.PROD,
    BASE_URL: import.meta.env.BASE_URL,
    location: window.location.href,
    userAgent: navigator.userAgent,
    timestamp: new Date().toISOString(),
    viewport: `${window.innerWidth}x${window.innerHeight}`,
    language: navigator.language,
    platform: navigator.platform,
    cookieEnabled: navigator.cookieEnabled,
    onLine: navigator.onLine,
    connectionType: navigator.connection?.effectiveType || 'unknown',
    downlink: navigator.connection?.downlink || 'unknown',
    rtt: navigator.connection?.rtt || 'unknown'
  };

  // Comprehensive endpoint testing function
  const testAllEndpoints = async () => {
    const results = {};
    const baseURL = import.meta.env.VITE_API_URL;
    
    if (!baseURL) {
      setEndpointTests({ error: 'VITE_API_URL not configured' });
      return;
    }

    setEndpointTests({ testing: true });
    
    for (const endpoint of endpoints) {
      const startTime = performance.now();
      try {
        const response = await fetch(`${baseURL}${endpoint.path}`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'X-Test-Request': 'true'
          },
          timeout: 10000
        });
        
        const endTime = performance.now();
        const responseTime = Math.round(endTime - startTime);
        
        let responseData = null;
        try {
          responseData = await response.json();
        } catch (e) {
          responseData = { error: 'Invalid JSON response' };
        }

        results[endpoint.name] = {
          status: response.status,
          ok: response.ok,
          responseTime,
          critical: endpoint.critical,
          path: endpoint.path,
          data: responseData,
          headers: Object.fromEntries(response.headers.entries()),
          error: response.ok ? null : `HTTP ${response.status}: ${response.statusText}`
        };
        
        // Add to real-time logs
        addLog(`${endpoint.name}: ${response.ok ? '✅' : '❌'} ${response.status} (${responseTime}ms)`);
        
      } catch (error) {
        const endTime = performance.now();
        const responseTime = Math.round(endTime - startTime);
        
        results[endpoint.name] = {
          status: 0,
          ok: false,
          responseTime,
          critical: endpoint.critical,
          path: endpoint.path,
          error: error.message,
          data: null
        };
        
        addLog(`${endpoint.name}: ❌ ${error.message} (${responseTime}ms)`);
      }
    }
    
    setEndpointTests(results);
    calculatePerformanceMetrics(results);
  };

  // Performance metrics calculation
  const calculatePerformanceMetrics = (results) => {
    const responseTimes = Object.values(results)
      .filter(r => r.responseTime && r.ok)
      .map(r => r.responseTime);
    
    const successCount = Object.values(results).filter(r => r.ok).length;
    const totalCount = Object.values(results).length;
    
    const metrics = {
      averageResponseTime: responseTimes.length > 0 
        ? Math.round(responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length)
        : 0,
      minResponseTime: responseTimes.length > 0 ? Math.min(...responseTimes) : 0,
      maxResponseTime: responseTimes.length > 0 ? Math.max(...responseTimes) : 0,
      successRate: ((successCount / totalCount) * 100).toFixed(1),
      criticalFailures: Object.values(results).filter(r => r.critical && !r.ok).length,
      totalEndpoints: totalCount,
      healthScore: ((successCount / totalCount) * 100).toFixed(0)
    };
    
    setPerformanceMetrics(metrics);
  };

  // Real-time logging system
  const addLog = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    setRealTimeLogs(prev => [
      { timestamp, message, id: Date.now() },
      ...prev.slice(0, 99) // Keep last 100 logs
    ]);
  };

  // Network diagnostics
  const runNetworkDiagnostics = async () => {
    const baseURL = import.meta.env.VITE_API_URL;
    if (!baseURL) return;

    try {
      const results = [];
      
      // DNS resolution test
      const dnsStart = performance.now();
      await fetch(`${baseURL}/health`, { method: 'HEAD' });
      const dnsTime = performance.now() - dnsStart;
      
      // Latency test with multiple requests
      const latencyTests = [];
      for (let i = 0; i < 5; i++) {
        const start = performance.now();
        await fetch(`${baseURL}/health`, { method: 'HEAD' });
        latencyTests.push(performance.now() - start);
      }
      
      const avgLatency = latencyTests.reduce((a, b) => a + b, 0) / latencyTests.length;
      
      setNetworkMetrics({
        dnsResolution: Math.round(dnsTime),
        averageLatency: Math.round(avgLatency),
        jitter: Math.round(Math.max(...latencyTests) - Math.min(...latencyTests)),
        connectionType: navigator.connection?.effectiveType || 'unknown',
        effectiveBandwidth: navigator.connection?.downlink || 'unknown',
        rtt: navigator.connection?.rtt || 'unknown'
      });
      
    } catch (error) {
      setNetworkMetrics({ error: error.message });
    }
  };

  // Security checks
  const runSecurityChecks = () => {
    const checks = {
      https: window.location.protocol === 'https:',
      cors: true, // Assume CORS is working if we can make requests
      csp: document.querySelector('meta[http-equiv="Content-Security-Policy"]') !== null,
      hsts: false, // Would need server response to check
      xssProtection: document.querySelector('meta[http-equiv="X-XSS-Protection"]') !== null,
      noSniff: true, // Assume modern browser
      frameOptions: document.querySelector('meta[http-equiv="X-Frame-Options"]') !== null
    };
    
    setSecurityChecks(checks);
  };

  // Auto-refresh mechanism
  useEffect(() => {
    if (autoRefresh && selectedTab === 0) {
      const interval = setInterval(() => {
        testAllEndpoints();
      }, refreshInterval);
      
      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval, selectedTab]);

  // Initial load
  useEffect(() => {
    testAllEndpoints();
    runNetworkDiagnostics();
    runSecurityChecks();
  }, []);

  // Export logs function
  const exportLogs = () => {
    const data = {
      timestamp: new Date().toISOString(),
      environment: environmentInfo,
      endpointTests,
      performanceMetrics,
      networkMetrics,
      securityChecks,
      logs: realTimeLogs
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `health-report-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Health check query
  const { data: healthData, isLoading: healthLoading, error: healthError, refetch: refetchHealth } = useQuery({
    queryKey: ['serviceHealth'],
    queryFn: healthCheck,
    refetchInterval: 30000, // Refresh every 30 seconds
    retry: 3
  });
  // API endpoint tests
  const testEndpoints = async () => {
    const endpoints = [
      { name: 'Health', fn: () => healthCheck() },
      { name: 'Stocks', fn: () => getStocks({ limit: 5 }) },
      { name: 'Technical', fn: () => getTechnicalData('daily', { limit: 5 }) },
      { name: 'Market', fn: () => getMarketOverview() },
      { name: 'Data Validation', fn: () => getDataValidationSummary() }
    ];

    const results = {};
    
    for (const endpoint of endpoints) {
      try {
        const startTime = Date.now();
        await endpoint.fn();
        const endTime = Date.now();
        results[endpoint.name] = {
          status: 'success',
          responseTime: endTime - startTime,
          error: null
        };
      } catch (error) {
        results[endpoint.name] = {
          status: 'error',
          responseTime: null,
          error: error.message
        };
      }
    }
    
    setTestResults(results);
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'success':
      case 'healthy':
      case 'connected':
        return <CheckCircle color="success" />;
      case 'error':
      case 'failed':
        return <Error color="error" />;
      case 'warning':
        return <Warning color="warning" />;
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
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'default';
    }
  };

  // Enhanced dashboard overview component
  const renderDashboardOverview = () => (
    <Grid container spacing={3}>
      {/* Health Score Card */}
      <Grid item xs={12} md={3}>
        <Card sx={{ 
          background: performanceMetrics.healthScore >= 90 
            ? 'linear-gradient(135deg, #4caf50 0%, #81c784 100%)'
            : performanceMetrics.healthScore >= 70
            ? 'linear-gradient(135deg, #ff9800 0%, #ffb74d 100%)'
            : 'linear-gradient(135deg, #f44336 0%, #e57373 100%)',
          color: 'white'
        }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <HealthAndSafety sx={{ fontSize: 40, mb: 1 }} />
            <Typography variant="h3" component="div">
              {performanceMetrics.healthScore || '0'}%
            </Typography>
            <Typography variant="body2">System Health</Typography>
          </CardContent>
        </Card>
      </Grid>

      {/* Response Time Card */}
      <Grid item xs={12} md={3}>
        <Card>
          <CardContent sx={{ textAlign: 'center' }}>
            <Speed sx={{ fontSize: 40, mb: 1, color: 'primary.main' }} />
            <Typography variant="h4" component="div">
              {performanceMetrics.averageResponseTime || '0'}ms
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Avg Response Time
            </Typography>
            {performanceMetrics.minResponseTime && (
              <Typography variant="caption" display="block">
                {performanceMetrics.minResponseTime}ms - {performanceMetrics.maxResponseTime}ms
              </Typography>
            )}
          </CardContent>
        </Card>
      </Grid>

      {/* Endpoints Status Card */}
      <Grid item xs={12} md={3}>
        <Card>
          <CardContent sx={{ textAlign: 'center' }}>
            <Api sx={{ fontSize: 40, mb: 1, color: 'secondary.main' }} />
            <Typography variant="h4" component="div">
              {Object.values(endpointTests).filter(t => t.ok).length}/{performanceMetrics.totalEndpoints || 0}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Endpoints Online
            </Typography>
            <Typography variant="caption" display="block">
              {performanceMetrics.successRate}% Success Rate
            </Typography>
          </CardContent>
        </Card>
      </Grid>

      {/* Critical Issues Card */}
      <Grid item xs={12} md={3}>
        <Card>
          <CardContent sx={{ textAlign: 'center' }}>
            <Warning sx={{ 
              fontSize: 40, 
              mb: 1, 
              color: performanceMetrics.criticalFailures > 0 ? 'error.main' : 'success.main' 
            }} />
            <Typography variant="h4" component="div">
              {performanceMetrics.criticalFailures || 0}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Critical Issues
            </Typography>
          </CardContent>
        </Card>
      </Grid>

      {/* Controls */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box display="flex" gap={2} alignItems="center" flexWrap="wrap">
              <FormControlLabel
                control={
                  <Switch
                    checked={autoRefresh}
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                  />
                }
                label="Auto Refresh"
              />
              
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Refresh Interval</InputLabel>
                <Select
                  value={refreshInterval}
                  onChange={(e) => setRefreshInterval(e.target.value)}
                  disabled={!autoRefresh}
                >
                  <MenuItem value={10000}>10 seconds</MenuItem>
                  <MenuItem value={30000}>30 seconds</MenuItem>
                  <MenuItem value={60000}>1 minute</MenuItem>
                  <MenuItem value={300000}>5 minutes</MenuItem>
                </Select>
              </FormControl>

              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={testAllEndpoints}
                disabled={endpointTests.testing}
              >
                {endpointTests.testing ? 'Testing...' : 'Test All'}
              </Button>

              <Button
                variant="outlined"
                startIcon={<NetworkCheck />}
                onClick={runNetworkDiagnostics}
              >
                Network Test
              </Button>

              <Button
                variant="outlined"
                startIcon={<Download />}
                onClick={exportLogs}
              >
                Export Report
              </Button>

              <Button
                variant="outlined"
                startIcon={<Visibility />}
                onClick={() => setLogViewOpen(true)}
              >
                View Logs ({realTimeLogs.length})
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  // Enhanced endpoint testing display
  const renderEndpointTests = () => (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
          <Api sx={{ mr: 1 }} />
          API Endpoint Tests
          {endpointTests.testing && <CircularProgress size={20} sx={{ ml: 2 }} />}
        </Typography>
        
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Endpoint</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Response Time</TableCell>
                <TableCell>Error</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {endpoints.map((endpoint) => {
                const result = endpointTests[endpoint.name];
                if (!result) return null;
                
                return (
                  <TableRow key={endpoint.name}>
                    <TableCell>
                      <Box display="flex" alignItems="center">
                        {endpoint.critical && (
                          <Tooltip title="Critical Endpoint">
                            <Warning color="warning" sx={{ mr: 1, fontSize: 16 }} />
                          </Tooltip>
                        )}
                        <Box>
                          <Typography variant="body2" fontWeight="bold">
                            {endpoint.name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {endpoint.path}
                          </Typography>
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip
                        icon={result.ok ? <CheckCircle /> : <Error />}
                        label={result.status}
                        color={result.ok ? 'success' : 'error'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {result.responseTime}ms
                      </Typography>
                      {result.responseTime > 1000 && (
                        <Chip label="Slow" color="warning" size="small" />
                      )}
                    </TableCell>
                    <TableCell>
                      {result.error && (
                        <Tooltip title={result.error}>
                          <Typography variant="caption" color="error" noWrap>
                            {result.error.substring(0, 30)}...
                          </Typography>
                        </Tooltip>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button
                        size="small"
                        onClick={() => {
                          setTestEndpoint(`${import.meta.env.VITE_API_URL}${endpoint.path}`);
                          testCustomEndpoint();
                        }}
                      >
                        Retest
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );

  // Network diagnostics display
  const renderNetworkDiagnostics = () => (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
          <NetworkCheck sx={{ mr: 1 }} />
          Network Diagnostics
        </Typography>
        
        {networkMetrics ? (
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="h6" color="primary">
                  {networkMetrics.dnsResolution || 'N/A'}ms
                </Typography>
                <Typography variant="caption">DNS Resolution</Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="h6" color="primary">
                  {networkMetrics.averageLatency || 'N/A'}ms
                </Typography>
                <Typography variant="caption">Average Latency</Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="h6" color="primary">
                  {networkMetrics.jitter || 'N/A'}ms
                </Typography>
                <Typography variant="caption">Jitter</Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="h6" color="primary">
                  {networkMetrics.connectionType || 'Unknown'}
                </Typography>
                <Typography variant="caption">Connection Type</Typography>
              </Paper>
            </Grid>
          </Grid>
        ) : (
          <Alert severity="info">Click "Network Test" to run diagnostics</Alert>
        )}
      </CardContent>
    </Card>
  );

  // Security checks display
  const renderSecurityChecks = () => (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
          <Security sx={{ mr: 1 }} />
          Security Checks
        </Typography>
        
        <List>
          {Object.entries(securityChecks).map(([check, passed]) => (
            <ListItem key={check}>
              <ListItemIcon>
                {passed ? <CheckCircle color="success" /> : <Error color="error" />}
              </ListItemIcon>
              <ListItemText
                primary={check.toUpperCase().replace(/([A-Z])/g, ' $1').trim()}
                secondary={passed ? 'Enabled' : 'Not configured'}
              />
            </ListItem>
          ))}
        </List>
      </CardContent>
    </Card>
  );

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
              >
                Refresh
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
                {environmentInfo?.VITE_API_URL ? 'Configured' : 'Not Configured'}
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
                {healthData?.database?.status === 'connected' ? 'Connected' : 'Unknown'}
              </Typography>
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
                {environmentInfo?.MODE || 'Unknown'}
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
              {healthData && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Status: {healthData.status}
                  </Typography>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    Last Updated: {new Date(healthData.timestamp).toLocaleString()}
                  </Typography>
                  
                  {healthData.api && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2">API Information:</Typography>
                      <Typography variant="body2">Version: {healthData.api.version}</Typography>
                      <Typography variant="body2">Environment: {healthData.api.environment}</Typography>
                    </Box>
                  )}
                </Box>
              )}
              
              <Box sx={{ mt: 2 }}>
                <Button 
                  variant="outlined" 
                  size="small" 
                  startIcon={<Speed />}
                  onClick={testEndpoints}
                >
                  Test All Endpoints
                </Button>
              </Box>

              {Object.keys(testResults).length > 0 && (
                <TableContainer component={Paper} sx={{ mt: 2 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Endpoint</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Response Time</TableCell>
                        <TableCell>Error</TableCell>
                      </TableRow>
                    </TableHead>                    <TableBody>
                      {testResults && typeof testResults === 'object' && Object.entries(testResults).map(([name, result]) => (
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
                            {result.responseTime ? `${result.responseTime}ms` : '-'}
                          </TableCell>
                          <TableCell>
                            {result.error || '-'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
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
            </AccordionSummary>
            <AccordionDetails>
              {healthData?.database && (
                <Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    {getStatusIcon(healthData.database.status)}
                    <Typography variant="subtitle2" sx={{ ml: 1 }}>
                      Status: {healthData.database.status}
                    </Typography>
                  </Box>
                  
                  <Typography variant="body2" gutterBottom>
                    Version: {healthData.database.version}
                  </Typography>

                  {healthData.database.tables && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>
                        Table Status:
                      </Typography>
                      <TableContainer component={Paper}>
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Table</TableCell>
                              <TableCell align="right">Records</TableCell>
                              <TableCell>Status</TableCell>
                            </TableRow>
                          </TableHead>                          <TableBody>
                            {healthData?.data?.database?.tables && typeof healthData.data.database.tables === 'object' && Object.entries(healthData.data.database.tables).map(([table, count]) => (
                              <TableRow key={table}>
                                <TableCell>{table}</TableCell>
                                <TableCell align="right">
                                  {typeof count === 'number' ? count.toLocaleString() : String(count)}
                                </TableCell>
                                <TableCell>
                                  <Chip
                                    icon={getStatusIcon(count === 'not_found' ? 'error' : 'success')}
                                    label={count === 'not_found' ? 'Missing' : 'Available'}
                                    color={getStatusColor(count === 'not_found' ? 'error' : 'success')}
                                    size="small"
                                  />
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>
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
              {environmentInfo && (
                <TableContainer component={Paper}>
                  <Table size="small">                    <TableBody>
                      {environmentInfo && typeof environmentInfo === 'object' && Object.entries(environmentInfo).map(([key, value]) => (
                        <TableRow key={key}>
                          <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                            {key}
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                              {String(value || 'undefined')}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </AccordionDetails>
          </Accordion>
        </Grid>

        {/* Error Information */}
        {(healthError || Object.values(testResults).some(r => r.status === 'error')) && (
          <Grid item xs={12} lg={6}>
            <Accordion>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6" color="error">
                  <Error sx={{ mr: 1, verticalAlign: 'middle' }} />
                  Error Details
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                {healthError && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    <Typography variant="subtitle2">Health Check Error:</Typography>
                    <Typography variant="body2">{healthError.message}</Typography>
                  </Alert>
                )}                  {testResults && typeof testResults === 'object' && Object.entries(testResults)
                  .filter(([, result]) => result?.status === 'error')
                  .map(([name, result]) => (
                    <Alert severity="error" key={name} sx={{ mb: 1 }}>
                      <Typography variant="subtitle2">{name} Endpoint Error:</Typography>
                      <Typography variant="body2">{result?.error || 'Unknown error'}</Typography>
                    </Alert>
                  ))}
              </AccordionDetails>
            </Accordion>
          </Grid>
        )}
      </Grid>
    </Container>
  );
}

export default ServiceHealth;
