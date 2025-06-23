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
  Button
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
  Speed
} from '@mui/icons-material';

// Import API functions
import {
  healthCheck,
  getDataValidationSummary,
  getTechnicalData,
  getStocks,
  getMarketOverview,
  testApiConnection,
  getBalanceSheet,
  getIncomeStatement,
  getCashFlowStatement,
  screenStocks,
  getBuySignals,
  getSellSignals,
  getEarningsEstimates,
  getNaaimData,
  getFearGreedData,
  getApiConfig,
  getDiagnosticInfo,
  getCurrentBaseURL
} from '../services/api';

// Utility: fetch with timeout for DB diagnostics
function fetchWithTimeout(resource, options = {}, timeout = 10000) {
  return Promise.race([
    fetch(resource, options),
    new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout after ' + timeout + 'ms')), timeout))
  ]);
}

function ServiceHealth() {  const [environmentInfo, setEnvironmentInfo] = useState({});
  const [testResults, setTestResults] = useState({});
  const [testingInProgress, setTestingInProgress] = useState(false);
  const [componentError, setComponentError] = useState(null);

  // Component error handler
  useEffect(() => {
    const handleError = (event) => {
      console.error('ServiceHealth component error:', event.error);
      setComponentError(event.error.message);
    };
    
    window.addEventListener('error', handleError);
    return () => window.removeEventListener('error', handleError);
  }, []);
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
  // Comprehensive endpoint tests
  const endpoints = [
    { name: 'Health', fn: () => healthCheck(), critical: true },
    { name: 'Health (Quick)', fn: () => healthCheck('?quick=true'), critical: true },
    { name: 'Database Health', fn: () => fetch(getCurrentBaseURL() + '/health/database').then(r => r.json()), critical: true },
    { name: 'Database Connection', fn: () => fetch(getCurrentBaseURL() + '/health/test-connection').then(r => r.json()), critical: true },
    { name: 'Database Diagnostics', fn: () => fetch(getCurrentBaseURL() + '/health/database/diagnostics').then(r => r.json()), critical: true },
    { name: 'Financial Tables Debug', fn: () => fetch(getCurrentBaseURL() + '/financials/debug/tables').then(r => r.json()), critical: false },
    { name: 'Technical Columns Debug', fn: () => fetch(getCurrentBaseURL() + '/technical/debug/columns').then(r => r.json()), critical: false },
    { name: 'API Connection', fn: () => testApiConnection(), critical: true },
    { name: 'Stocks', fn: () => getStocks({ limit: 5 }), critical: true },
    { name: 'Technical Daily', fn: () => getTechnicalData('daily', { limit: 5 }), critical: true },
    { name: 'Technical Weekly', fn: () => getTechnicalData('weekly', { limit: 5 }), critical: false },
    { name: 'Technical Monthly', fn: () => getTechnicalData('monthly', { limit: 5 }), critical: false },
    { name: 'Market Overview', fn: () => getMarketOverview(), critical: true },
    { name: 'Data Validation', fn: () => getDataValidationSummary(), critical: true },
    { name: 'Stock Screener', fn: () => screenStocks({ limit: 5 }), critical: true },
    { name: 'Balance Sheet', fn: () => getBalanceSheet('AAPL'), critical: false },
    { name: 'Income Statement', fn: () => getIncomeStatement('AAPL'), critical: false },
    { name: 'Cash Flow', fn: () => getCashFlowStatement('AAPL'), critical: false },
    { name: 'Buy Signals', fn: () => getBuySignals({ limit: 5 }), critical: false },
    { name: 'Sell Signals', fn: () => getSellSignals({ limit: 5 }), critical: false },
    { name: 'Earnings Estimates', fn: () => getEarningsEstimates({ limit: 5 }), critical: false },
    { name: 'NAAIM Data', fn: () => getNaaimData({ limit: 5 }), critical: false },
    { name: 'Fear & Greed', fn: () => getFearGreedData({ limit: 5 }), critical: false }
  ];

  // Test all endpoints
  const testAllEndpoints = async () => {
    setTestingInProgress(true);
    const results = {};
    
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
      setTestResults(results);
    setTestingInProgress(false);  };

  // Health check query
  const { data: healthData, isLoading: healthLoading, error: healthError, refetch: refetchHealth } = useQuery({
    queryKey: ['serviceHealth'],
    queryFn: async () => {
      console.log('=== HEALTH CHECK ===');
      console.log('Testing health endpoint:', getCurrentBaseURL() + '/health');
      
      try {
        const result = await healthCheck();
        console.log('Health check success:', result);
        return result;
      } catch (error) {
        console.error('Health check failed:', error);
        throw error;
      }
    },
    refetchInterval: false, // Don't auto-refresh to avoid spam
    retry: 1,
    staleTime: 30000,
    enabled: false // Don't auto-run, only run when manually triggered
  });// Database diagnostics query
  const { data: dbDiagnostics, isLoading: dbLoading, error: dbError, refetch: refetchDb } = useQuery({
    queryKey: ['databaseDiagnostics'],
    queryFn: async () => {
      const url = getCurrentBaseURL() + '/health/database/diagnostics';
      console.log('Fetching database diagnostics from:', url);
      let response;
      try {
        response = await fetchWithTimeout(url, { method: 'GET', headers: { 'Content-Type': 'application/json' } }, 10000);
      } catch (err) {
        throw new Error(`Failed to fetch ${url}: ${err.message}`);
      }
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${response.statusText} - ${errorText}`);
      }
      const data = await response.json();
      if (!data || typeof data !== 'object' || (!data.diagnostics && !data.summary)) {
        throw new Error('Unexpected diagnostics API response structure: ' + JSON.stringify(data));
      }
      return data;
    },
    refetchInterval: false, // Don't auto-refresh to avoid spam
    retry: 1, // Only retry once
    staleTime: 30000,
    enabled: true // Auto-run on mount so diagnostics load automatically
  });
  // Gather environment information
  useEffect(() => {
    const apiConfig = getApiConfig()
    const diagnosticInfo = getDiagnosticInfo()
    
    console.log('=== SERVICE HEALTH DEBUG INFO ===')
    console.log('API Config:', apiConfig)
    console.log('Diagnostic Info:', diagnosticInfo)
    console.log('Current Base URL:', getCurrentBaseURL())
    console.log('Window Location:', window.location.href)
    console.log('Environment Variables:', import.meta.env)
    
    const env = {
      Frontend: {
        ...apiConfig,
        location: window.location.href,
        userAgent: navigator.userAgent.substring(0, 100) + '...',
        timestamp: new Date().toISOString(),
        viteApiUrl: import.meta.env.VITE_API_URL,
        currentBaseURL: getCurrentBaseURL(),
        diagnosticInfo: diagnosticInfo
      }
    };
    setEnvironmentInfo(env);
    
    // Auto-run tests on component mount
    testAllEndpoints();
  }, []);

  // Combine environment info with database diagnostics
  const combinedEnvironmentInfo = {
    ...environmentInfo,
    Backend: dbDiagnostics?.diagnostics?.environment || {},
    Database: dbDiagnostics?.summary || {}
  };

  // Get diagnostic information
  const diagnosticInfo = getDiagnosticInfo()

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
        </Grid>        <Grid item xs={12} md={3}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Api sx={{ fontSize: 40, mb: 1, color: 'primary.main' }} />
              <Typography variant="h6">
                API Gateway
              </Typography>
              <Typography variant="body2" color="textSecondary">
                {diagnosticInfo?.isConfigured ? 'Configured' : 'Not Configured'}
              </Typography>
              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                {diagnosticInfo?.urlsMatch ? 'URLs Match' : 'URL Mismatch'}
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
                {(dbDiagnostics && dbDiagnostics.diagnostics && dbDiagnostics.diagnostics.connection?.status === 'connected') ? 'Connected' :
                 healthData?.database?.status === 'connected' ? 'Connected' :
                 dbLoading ? 'Checking...' : 'Unknown'}
              </Typography>
              {(dbDiagnostics && dbDiagnostics.diagnostics && dbDiagnostics.diagnostics.database?.name) && (
                <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                  {dbDiagnostics.diagnostics.database.name}
                </Typography>
              )}
              {dbError && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  Failed to load database diagnostics: {dbError.message}
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
                {/* Show a friendly environment name. Default to 'Production' if not set. */}
                {(() => {
                  const env = import.meta.env.VITE_ENV || import.meta.env.MODE || '';
                  if (env.toLowerCase().startsWith('prod')) return 'Production';
                  if (env.toLowerCase().startsWith('stag')) return 'Staging';
                  if (env.toLowerCase().startsWith('dev')) return 'Development';
                  if (env) return env.charAt(0).toUpperCase() + env.slice(1);
                  return 'Production';
                })()}
              </Typography>
              <Typography variant="caption" display="block" sx={{ mt: 1 }} title={import.meta.env.VITE_API_URL || ''}>
                {import.meta.env.VITE_API_URL ? `API: ${import.meta.env.VITE_API_URL}` : ''}
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
                  onClick={testAllEndpoints}
                  disabled={testingInProgress}
                >
                  {testingInProgress ? 'Testing...' : 'Test All Endpoints'}
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
                        <TableCell>Error</TableCell>                      </TableRow>
                    </TableHead>
                    <TableBody>
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
              <Button 
                variant="outlined" 
                size="small" 
                startIcon={<Refresh />}
                onClick={refetchDb}
                sx={{ ml: 'auto', mr: 2 }}
                disabled={dbLoading}
              >
                {dbLoading ? 'Loading...' : 'Refresh'}
              </Button>
            </AccordionSummary>
            <AccordionDetails>
              {dbLoading && (
                <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                  <CircularProgress size={24} />
                  <Typography sx={{ ml: 2 }}>Loading database diagnostics...</Typography>
                </Box>
              )}
              
              {dbError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <Typography variant="subtitle2">Failed to load database diagnostics:</Typography>
                  <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                    {dbError.message || String(dbError)}
                  </Typography>
                  <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mt: 1, wordBreak: 'break-all' }}>
                    Endpoint: {getCurrentBaseURL() + '/health/database/diagnostics'}
                  </Typography>
                </Alert>
              )}
              {(dbDiagnostics && dbDiagnostics.diagnostics) && (
                <Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    {getStatusIcon(dbDiagnostics.diagnostics.connection.status)}
                    <Typography variant="subtitle2" sx={{ ml: 1 }}>
                      Status: {dbDiagnostics.diagnostics.connection.status}
                    </Typography>
                  </Box>
                  
                  <Typography variant="body2" gutterBottom>
                    Database: {dbDiagnostics.diagnostics.database.name}
                  </Typography>
                  
                  <Typography variant="body2" gutterBottom>
                    Version: {dbDiagnostics.diagnostics.database.version}
                  </Typography>

                  <Typography variant="body2" gutterBottom>
                    Connection: {dbDiagnostics.diagnostics.connection.method}
                  </Typography>

                  <Typography variant="body2" gutterBottom>
                    Environment: {dbDiagnostics.diagnostics.environment.NODE_ENV}
                  </Typography>

                  {dbDiagnostics.diagnostics.tables && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>
                        Table Status ({dbDiagnostics.diagnostics.tables.withData}/{dbDiagnostics.diagnostics.tables.total} with data):
                      </Typography>
                      <TableContainer component={Paper} sx={{ maxHeight: 300 }}>
                        <Table size="small" stickyHeader>
                          <TableHead>
                            <TableRow>
                              <TableCell>Table</TableCell>
                              <TableCell align="right">Records</TableCell>
                              <TableCell align="right">Columns</TableCell>
                              <TableCell>Status</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {dbDiagnostics.diagnostics.tables.list?.map((table) => (
                              <TableRow key={table.table_name}>
                                <TableCell>{table.table_name}</TableCell>
                                <TableCell align="right">
                                  {typeof table.record_count === 'number' ? table.record_count.toLocaleString() : String(table.record_count)}
                                </TableCell>
                                <TableCell align="right">
                                  {table.column_count}
                                </TableCell>
                                <TableCell>
                                  <Chip
                                    icon={getStatusIcon(table.record_count > 0 ? 'success' : 'warning')}
                                    label={table.record_count > 0 ? 'Has Data' : 'Empty'}
                                    color={getStatusColor(table.record_count > 0 ? 'success' : 'warning')}
                                    size="small"
                                  />
                                </TableCell>
                              </TableRow>
                            )) || []}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Box>
                  )}
                </Box>
              )}
              
              {/* Fallback debug info if diagnostics are missing or malformed */}
              {!(dbDiagnostics && dbDiagnostics.diagnostics) && !dbLoading && !dbError && (
                <Alert severity="info" sx={{ mb: 2 }}>
                  Database diagnostics not available. Check if backend is properly deployed.<br />
                  <Typography variant="caption" sx={{ display: 'block', mt: 1, wordBreak: 'break-all' }}>
                    Raw diagnostics object: {dbDiagnostics ? JSON.stringify(dbDiagnostics, null, 2) : 'undefined'}
                  </Typography>
                </Alert>
              )}
              
              {healthData?.database && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    Basic Database Status:
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    {getStatusIcon(healthData.database.status)}
                    <Typography variant="body2" sx={{ ml: 1 }}>
                      Status: {healthData.database.status}
                    </Typography>
                  </Box>
                  {healthData.database.responseTime && (
                    <Typography variant="body2">
                      Response Time: {healthData.database.responseTime}ms
                    </Typography>
                  )}
                  {healthData.database.error && (
                    <Typography variant="body2" color="error">
                      Error: {healthData.database.error}
                    </Typography>
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
              {combinedEnvironmentInfo && (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableBody>
                      {combinedEnvironmentInfo && typeof combinedEnvironmentInfo === 'object' && Object.entries(combinedEnvironmentInfo).map(([section, values]) => (
                        <React.Fragment key={section}>
                          <TableRow>
                            <TableCell colSpan={2} sx={{ fontWeight: 'bold', backgroundColor: 'grey.100' }}>
                              {section}
                            </TableCell>
                          </TableRow>
                          {values && typeof values === 'object' && Object.entries(values).map(([key, value]) => (
                            <TableRow key={`${section}-${key}`}>
                              <TableCell component="th" scope="row" sx={{ fontWeight: 'bold', pl: 3 }}>
                                {key}
                              </TableCell>
                              <TableCell>
                                <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                                  {String(value || 'undefined')}
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
              {diagnosticInfo && (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          Current API URL
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {diagnosticInfo.currentApiUrl || 'Not set'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          Axios Default Base URL
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {diagnosticInfo.axiosDefaultBaseUrl || 'Not set'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          VITE_API_URL
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                            {diagnosticInfo.viteApiUrl || 'Not set'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                          URLs Match
                        </TableCell>
                        <TableCell>
                          <Chip
                            icon={getStatusIcon(diagnosticInfo.urlsMatch ? 'success' : 'error')}
                            label={diagnosticInfo.urlsMatch ? 'Yes' : 'No'}
                            color={getStatusColor(diagnosticInfo.urlsMatch ? 'success' : 'error')}
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
                            icon={getStatusIcon(diagnosticInfo.isConfigured ? 'success' : 'error')}
                            label={diagnosticInfo.isConfigured ? 'Yes' : 'No'}
                            color={getStatusColor(diagnosticInfo.isConfigured ? 'success' : 'error')}
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
                )}
                {testResults && typeof testResults === 'object' && Object.entries(testResults)
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
      </Grid>      {/* Redundant API connectivity test removed */}
    </Container>
  );
}

export default ServiceHealth;
