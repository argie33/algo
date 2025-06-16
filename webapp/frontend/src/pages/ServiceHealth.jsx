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
  testApiConnection
} from '../services/api';

function ServiceHealth() {
  const [environmentInfo, setEnvironmentInfo] = useState(null);
  const [apiTest, setApiTest] = useState(null);
  const [testResults, setTestResults] = useState({});

  useEffect(() => {
    // Gather environment information
    const env = {
      VITE_API_URL: import.meta.env.VITE_API_URL,
      MODE: import.meta.env.MODE,
      DEV: import.meta.env.DEV,
      PROD: import.meta.env.PROD,
      BASE_URL: import.meta.env.BASE_URL,
      location: window.location.href,
      userAgent: navigator.userAgent,
      timestamp: new Date().toISOString()
    };
    setEnvironmentInfo(env);
  }, []);
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
                      {testResults && Object.entries(testResults).map(([name, result]) => (
                        <TableRow key={name}>
                          <TableCell>{name}</TableCell>
                          <TableCell>
                            <Chip
                              icon={getStatusIcon(result.status)}
                              label={result.status}
                              color={getStatusColor(result.status)}
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
                            {healthData?.data?.database?.tables && Object.entries(healthData.data.database.tables).map(([table, count]) => (
                              <TableRow key={table}>
                                <TableCell>{table}</TableCell>
                                <TableCell align="right">
                                  {typeof count === 'number' ? count.toLocaleString() : count}
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
                      {environmentInfo && Object.entries(environmentInfo).map(([key, value]) => (
                        <TableRow key={key}>
                          <TableCell component="th" scope="row" sx={{ fontWeight: 'bold' }}>
                            {key}
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                              {String(value)}
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
                )}
                  {testResults && Object.entries(testResults)
                  .filter(([, result]) => result.status === 'error')
                  .map(([name, result]) => (
                    <Alert severity="error" key={name} sx={{ mb: 1 }}>
                      <Typography variant="subtitle2">{name} Endpoint Error:</Typography>
                      <Typography variant="body2">{result.error}</Typography>
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
