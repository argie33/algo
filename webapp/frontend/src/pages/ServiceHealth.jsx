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

  // Cached database health check - uses the backend's cached health_status table
  const { data: dbHealth, isLoading: dbLoading, error: dbError, refetch: refetchDb } = useQuery({
    queryKey: ['databaseHealth'],
    queryFn: async () => {
      try {
        console.log('Starting cached database health check...');
        
        // Use the standard api instance but with better error handling
        const response = await api.get('/health/database', {
          timeout: 15000, // 15 second timeout
          validateStatus: (status) => status < 500 // Don't throw on 4xx errors
        });
        
        console.log('Database health response:', response.data);
        console.log('Response structure:', {
          hasData: !!response.data,
          hasDatabase: !!response.data?.database,
          hasTables: !!response.data?.database?.tables,
          hasSummary: !!response.data?.database?.summary,
          tableCount: response.data?.database?.tables ? Object.keys(response.data.database.tables).length : 0
        });
        
        // Ensure we return a proper object structure
        if (response.data && typeof response.data === 'object') {
          return response.data;
        } else {
          throw new Error('Invalid response structure from database health endpoint');
        }
        
      } catch (error) {
        console.error('Database health check failed:', error);
        console.error('Error details:', {
          message: error.message,
          response: error.response?.data,
          status: error.response?.status
        });
        
        // Return a structured error object instead of throwing
        return {
          error: true,
          message: error.message || 'Unknown database health error',
          details: error.response?.data || error.response?.status || 'No additional details',
          timestamp: new Date().toISOString(),
          // Provide fallback data structure that matches the expected format
          database: { 
            status: 'error',
            currentTime: new Date().toISOString(),
            postgresVersion: 'unknown',
            tables: {},
            summary: { 
              total_tables: 0, 
              healthy_tables: 0, 
              stale_tables: 0, 
              empty_tables: 0,
              error_tables: 1,
              missing_tables: 0,
              total_records: 0,
              total_missing_data: 0
            }
          }
        };
      }
    },
    refetchInterval: false,
    retry: 1,
    staleTime: 30000,
    enabled: true, // Auto-run on mount
    // Add error handling to prevent React Query from throwing
    onError: (error) => {
      console.error('React Query database health error:', error);
    }
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
      await api.post('/health/update-status');
      
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
                      <Typography variant="subtitle2" gutterBottom>Table Details ({Object.keys(safeDbHealth.database.tables).length} tables):</Typography>
                      <TableContainer component={Paper} sx={{ maxHeight: 400 }}>
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
                            {Object.entries(safeDbHealth.database.tables).map(([tableName, tableData]) => (
                              <TableRow key={tableName}>
                                <TableCell component="th" scope="row">
                                  <Typography variant="body2" fontFamily="monospace">
                                    {tableName}
                                  </Typography>
                                </TableCell>
                                <TableCell align="right">
                                  <Typography variant="body2">
                                    {formatNumber(tableData.record_count)}
                                  </Typography>
                                </TableCell>
                                <TableCell>
                                  <Chip
                                    icon={getStatusIcon(tableData.status)}
                                    label={tableData.status}
                                    color={getStatusColor(tableData.status)}
                                    size="small"
                                  />
                                  {tableData.is_stale && (
                                    <Chip
                                      label="Stale"
                                      color="warning"
                                      size="small"
                                      sx={{ ml: 0.5 }}
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
                                    <Typography variant="body2" color="warning.main">
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
