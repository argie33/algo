import React, { useState, useEffect } from 'react';
import { 
  Card, 
  CardContent, 
  Typography, 
  Grid, 
  Box, 
  Chip, 
  CircularProgress,
  Button,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip
} from '@mui/material';
import { 
  CheckCircle, 
  Error, 
  Warning, 
  Refresh,
  Info,
  Storage,
  Api,
  Memory
} from '@mui/icons-material';
import { api } from '../services/api';

const ServiceHealth = () => {
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchHealthData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [basicHealth, dbHealth] = await Promise.all([
        api.get('/health'),
        api.get('/health/database').catch(err => ({ 
          data: { 
            status: 'error', 
            database: { status: 'error', error: err.message } 
          } 
        }))
      ]);

      setHealthData({
        basic: basicHealth.data,
        database: dbHealth.data
      });
    } catch (err) {
      console.error('Error fetching health data:', err);
      setError(err.message || 'Failed to fetch health data');
    } finally {
      setLoading(false);
    }
  };

  const refreshHealthStatus = async () => {
    try {
      setRefreshing(true);
      await api.post('/health/update-status');
      await fetchHealthData(); // Refresh the display
    } catch (err) {
      console.error('Error refreshing health status:', err);
      setError('Failed to refresh health status: ' + err.message);
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchHealthData();
  }, []);

  const getStatusIcon = (status) => {
    switch (status) {
      case 'healthy':
      case 'connected':
      case 'ok':
        return <CheckCircle color="success" />;
      case 'error':
      case 'disconnected':
      case 'unhealthy':
        return <Error color="error" />;
      case 'warning':
      case 'degraded':
      case 'not_found':
        return <Warning color="warning" />;
      default:
        return <Info color="info" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy':
      case 'connected':
      case 'ok':
        return 'success';
      case 'error':
      case 'disconnected':
      case 'unhealthy':
        return 'error';
      case 'warning':
      case 'degraded':
      case 'not_found':
        return 'warning';
      default:
        return 'info';
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

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1">
          Service Health Dashboard
        </Typography>
        <Button
          variant="contained"
          startIcon={<Refresh />}
          onClick={refreshHealthStatus}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing...' : 'Refresh Health Status'}
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Basic Health Status */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={2}>
                <Api sx={{ mr: 1 }} />
                <Typography variant="h6">API Health</Typography>
              </Box>
              
              {healthData?.basic && (
                <Box>
                  <Box display="flex" alignItems="center" mb={1}>
                    {getStatusIcon(healthData.basic.status)}
                    <Typography variant="body1" sx={{ ml: 1 }}>
                      Status: {healthData.basic.status}
                    </Typography>
                  </Box>
                  
                  <Typography variant="body2" color="text.secondary">
                    Environment: {healthData.basic.api?.environment || 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Version: {healthData.basic.api?.version || 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Uptime: {healthData.basic.uptime ? `${Math.round(healthData.basic.uptime / 60)} minutes` : 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Memory: {healthData.basic.memory ? `${Math.round(healthData.basic.memory.heapUsed / 1024 / 1024)}MB` : 'N/A'}
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Database Health Status */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={2}>
                <Storage sx={{ mr: 1 }} />
                <Typography variant="h6">Database Health</Typography>
              </Box>
              
              {healthData?.database && (
                <Box>
                  <Box display="flex" alignItems="center" mb={1}>
                    {getStatusIcon(healthData.database.database?.status)}
                    <Typography variant="body1" sx={{ ml: 1 }}>
                      Status: {healthData.database.database?.status || 'Unknown'}
                    </Typography>
                  </Box>
                  
                  <Typography variant="body2" color="text.secondary">
                    Current Time: {formatDate(healthData.database.database?.currentTime)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    PostgreSQL: {healthData.database.database?.postgresVersion?.split(' ')[0] || 'N/A'}
                  </Typography>
                  
                  {healthData.database.database?.note && (
                    <Alert severity="info" sx={{ mt: 1 }}>
                      {healthData.database.database.note}
                    </Alert>
                  )}
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Table Status */}
        {healthData?.database?.database?.tables && (
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" mb={2}>
                  Database Tables Status
                </Typography>
                
                <TableContainer component={Paper} variant="outlined">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Table Name</TableCell>
                        <TableCell align="right">Record Count</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Last Checked</TableCell>
                        <TableCell>Error</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {Object.entries(healthData.database.database.tables).map(([tableName, tableData]) => (
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
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    </Box>
  );
};

export default ServiceHealth;
