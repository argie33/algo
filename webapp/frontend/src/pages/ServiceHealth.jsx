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
  Speed,
  Memory
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

function isObject(val) {
  return val && typeof val === 'object' && !Array.isArray(val);
}

function ServiceHealth() {
  const [environmentInfo, setEnvironmentInfo] = useState({});
  const [testResults, setTestResults] = useState({});
  const [testingInProgress, setTestingInProgress] = useState(false);
  const [componentError, setComponentError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Memoize diagnosticInfo to prevent infinite re-renders
  const diagnosticInfo = useMemo(() => getDiagnosticInfo(), []);
  
  // Memoize other API config calls to prevent infinite re-renders
  const apiConfig = useMemo(() => getApiConfig(), []);
  const currentBaseURL = useMemo(() => getCurrentBaseURL(), []);

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

  // Simplified endpoint tests - only test essential endpoints
  const endpoints = useMemo(() => [
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

  // Test all endpoints
  const testAllEndpoints = useCallback(async () => {
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
    setTestingInProgress(false);
  }, [endpoints]);

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

  // Cached database health check - uses new cached system
  const { data: dbHealth, isLoading: dbLoading, error: dbError, refetch: refetchDb } = useQuery({
    queryKey: ['databaseHealth'],
    queryFn: async () => {
      try {
        // Use the new cached database health endpoint
        const response = await fetch(getCurrentBaseURL() + '/health/database', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: AbortSignal.timeout(10000) // 10 second timeout
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        return data;
      } catch (error) {
        console.error('Database health check failed:', error);
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
      await fetch(getCurrentBaseURL() + '/health/update-status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(30000) // 30 second timeout for background job
      });
      await refetchDb(); // Refresh the display
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
        viteApiUrl: import.meta.env.VITE_API_URL,
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
      case 'disconnected':
        return 'error';
      case 'warning':
        return 'warning';
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
                {safeDbHealth?.database?.status === 'connected' ? 'Connected' :
                 safeDbHealth?.database?.status === 'disconnected' ? 'Disconnected' :
                 dbLoading ? 'Checking...' : 'Unknown'}
              </Typography>
              {dbError && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  Failed to load database health: {dbError.message}
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
                onClick={refreshHealthStatus}
                sx={{ ml: 'auto', mr: 2 }}
                disabled={refreshing}
              >
                {refreshing ? 'Updating...' : 'Update Status'}
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
                    {dbError.message || String(dbError)}
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

                  {safeDbHealth.database?.tables && Object.keys(safeDbHealth.database.tables).length > 0 && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2" gutterBottom>Table Status (Cached):</Typography>
                      <TableContainer component={Paper} sx={{ maxHeight: 300 }}>
                        <Table size="small" stickyHeader>
                          <TableHead>
                            <TableRow>
                              <TableCell>Table</TableCell>
                              <TableCell align="right">Records</TableCell>
                              <TableCell>Status</TableCell>
                              <TableCell>Last Checked</TableCell>
                              <TableCell>Error</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {Object.entries(safeDbHealth.database.tables).map(([tableName, tableData]) => (
                              <TableRow key={tableName}>
                                <TableCell>{tableName}</TableCell>
                                <TableCell align="right">
                                  {formatNumber(tableData.record_count)}
                                </TableCell>
                                <TableCell>
                                  <Chip
                                    icon={getStatusIcon(tableData.status)}
                                    label={tableData.status}
                                    color={getStatusColor(tableData.status)}
                                    size="small"
                                  />
                                </TableCell>
                                <TableCell>
                                  {formatDate(tableData.last_checked)}
                                </TableCell>
                                <TableCell>
                                  {tableData.error && (
                                    <Tooltip title={tableData.error}>
                                      <Typography variant="body2" color="error" sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {tableData.error}
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

        {/* Error Information */}
        {(healthError || Object.values(safeTestResults).some(r => r.status === 'error')) && (
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
                {Object.entries(safeTestResults)
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
