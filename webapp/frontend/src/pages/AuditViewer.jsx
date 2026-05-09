import React, { useState } from 'react';
import { useApiQuery } from '../hooks/useApiQuery';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Paper,
  Card,
  CardContent,
  Grid,
  TextField,
  MenuItem,
  Button,
  Pagination,
  CircularProgress,
  Box,
  Typography,
  Chip,
  Tabs,
  Tab
} from '@mui/material';
import { getApiConfig } from '../services/api';

const AuditViewer = () => {
  const { apiUrl: API_BASE_URL } = getApiConfig();
  const [currentTab, setCurrentTab] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [filters, setFilters] = useState({
    symbol: '',
  });

  // Fetch trade audit logs
  const {
    data: tradeAuditData,
    loading: tradeAuditLoading,
    error: tradeAuditError,
    refetch: refetchTradeAudit
  } = useApiQuery(
    ['auditTrades', page, limit, filters],
    async () => {
      const params = new URLSearchParams({
        limit,
        offset: (page - 1) * limit
      });
      if (filters.symbol) params.append('symbol', filters.symbol);

      const response = await fetch(`${API_BASE_URL}/api/audit/trades?${params}`);
      if (!response.ok) throw new Error('Failed to fetch trade audit logs');
      return response.json();
    },
    { staleTime: 30000 }
  );

  // Fetch safeguard audit logs
  const {
    data: safeguardAuditData,
    loading: safeguardAuditLoading,
    error: safeguardAuditError,
  } = useApiQuery(
    ['auditSafeguards', page, limit, filters],
    async () => {
      const params = new URLSearchParams({
        limit,
        offset: (page - 1) * limit
      });
      if (filters.symbol) params.append('symbol', filters.symbol);

      const response = await fetch(`${API_BASE_URL}/api/audit/safeguards?${params}`);
      if (!response.ok) throw new Error('Failed to fetch safeguard audit logs');
      return response.json();
    },
    { staleTime: 30000 }
  );

  // Fetch config audit logs
  const {
    data: configAuditData,
    loading: configAuditLoading,
    error: configAuditError,
  } = useApiQuery(
    ['auditConfig', page, limit],
    async () => {
      const params = new URLSearchParams({
        limit,
        offset: (page - 1) * limit
      });

      const response = await fetch(`${API_BASE_URL}/api/audit/config?${params}`);
      if (!response.ok) throw new Error('Failed to fetch config audit logs');
      return response.json();
    },
    { staleTime: 30000 }
  );

  // Fetch audit summary
  const {
    data: summaryData,
  } = useApiQuery(
    ['auditSummary'],
    async () => {
      const response = await fetch(`${API_BASE_URL}/api/audit/summary`);
      if (!response.ok) throw new Error('Failed to fetch summary');
      return response.json();
    },
    { staleTime: 30000 }
  );

  const summary = summaryData?.data || {};
  const tradeAudits = tradeAuditData?.data || [];
  const tradePagination = tradeAuditData?.pagination || {};
  const safeguardAudits = safeguardAuditData?.data || [];
  const safeguardPagination = safeguardAuditData?.pagination || {};
  const configAudits = configAuditData?.data || [];
  const configPagination = configAuditData?.pagination || {};

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed':
      case 'success':
        return 'success';
      case 'pending':
        return 'info';
      case 'failed':
      case 'error':
        return 'error';
      default:
        return 'default';
    }
  };

  const handleFilterChange = (field, value) => {
    setFilters(prev => ({
      ...prev,
      [field]: value
    }));
    setPage(1);
  };

  const handleReset = () => {
    setFilters({ symbol: '' });
    setPage(1);
  };

  const isLoading = tradeAuditLoading || safeguardAuditLoading || configAuditLoading;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" sx={{ mb: 3 }}>
        Audit Trail Viewer
      </Typography>

      {/* Summary Cards */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Trade Actions
              </Typography>
              <Typography variant="h5">
                {summary.trade_actions || 0}
              </Typography>
              {summary.last_trade_action && (
                <Typography variant="caption">
                  Last: {formatDate(summary.last_trade_action)}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Config Changes
              </Typography>
              <Typography variant="h5">
                {summary.config_changes || 0}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Safeguard Activations
              </Typography>
              <Typography variant="h5">
                {summary.safeguard_activations || 0}
              </Typography>
              {summary.last_safeguard && (
                <Typography variant="caption">
                  Last: {formatDate(summary.last_safeguard)}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth
              size="small"
              label="Filter by Symbol"
              value={filters.symbol}
              onChange={(e) => handleFilterChange('symbol', e.target.value.toUpperCase())}
              placeholder="e.g., AAPL"
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <Button
              variant="outlined"
              size="small"
              onClick={handleReset}
              fullWidth
            >
              Reset Filters
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {/* Tabs */}
      <Paper sx={{ mb: 3 }}>
        <Tabs
          value={currentTab}
          onChange={(e, newValue) => {
            setCurrentTab(newValue);
            setPage(1);
          }}
        >
          <Tab label="Trade Actions" />
          <Tab label="Safeguard Activations" />
          <Tab label="Config Changes" />
        </Tabs>

        {/* Trade Audit Tab */}
        {currentTab === 0 && (
          <Box sx={{ p: 2 }}>
            {tradeAuditLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                <CircularProgress />
              </Box>
            ) : tradeAuditError ? (
              <Typography color="error">{tradeAuditError}</Typography>
            ) : (
              <>
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                        <TableCell>Date</TableCell>
                        <TableCell>Action</TableCell>
                        <TableCell>Symbol</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Details</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {tradeAudits.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5} align="center" sx={{ py: 3 }}>
                            No trade audit logs found
                          </TableCell>
                        </TableRow>
                      ) : (
                        tradeAudits.map((log, idx) => (
                          <TableRow key={idx} hover>
                            <TableCell>{formatDate(log.created_at)}</TableCell>
                            <TableCell>
                              <Chip
                                label={log.action_type}
                                size="small"
                                variant="outlined"
                              />
                            </TableCell>
                            <TableCell>{log.symbol || 'N/A'}</TableCell>
                            <TableCell>
                              <Chip
                                label={log.status}
                                size="small"
                                color={getStatusColor(log.status)}
                              />
                            </TableCell>
                            <TableCell>
                              {log.error_message ? (
                                <Typography variant="caption" color="error">
                                  {log.error_message}
                                </Typography>
                              ) : (
                                <Typography variant="caption">
                                  {log.details ? JSON.stringify(log.details).substring(0, 50) : 'N/A'}
                                </Typography>
                              )}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </Box>
                {tradePagination.total > 0 && (
                  <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                    <Pagination
                      page={page}
                      count={Math.ceil(tradePagination.total / limit)}
                      onChange={(e, p) => setPage(p)}
                    />
                  </Box>
                )}
              </>
            )}
          </Box>
        )}

        {/* Safeguard Audit Tab */}
        {currentTab === 1 && (
          <Box sx={{ p: 2 }}>
            {safeguardAuditLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                <CircularProgress />
              </Box>
            ) : safeguardAuditError ? (
              <Typography color="error">{safeguardAuditError}</Typography>
            ) : (
              <>
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                        <TableCell>Date</TableCell>
                        <TableCell>Symbol</TableCell>
                        <TableCell>Safeguard</TableCell>
                        <TableCell>Decision</TableCell>
                        <TableCell>Reason</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {safeguardAudits.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5} align="center" sx={{ py: 3 }}>
                            No safeguard audit logs found
                          </TableCell>
                        </TableRow>
                      ) : (
                        safeguardAudits.map((log, idx) => (
                          <TableRow key={idx} hover>
                            <TableCell>{formatDate(log.timestamp)}</TableCell>
                            <TableCell>{log.symbol}</TableCell>
                            <TableCell>
                              <Chip label={log.safeguard} size="small" variant="outlined" />
                            </TableCell>
                            <TableCell>
                              <Chip
                                label={log.decision}
                                size="small"
                                color={log.decision === 'BLOCKED' ? 'error' : 'success'}
                              />
                            </TableCell>
                            <TableCell>{log.reason}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </Box>
                {safeguardPagination.total > 0 && (
                  <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                    <Pagination
                      page={page}
                      count={Math.ceil(safeguardPagination.total / limit)}
                      onChange={(e, p) => setPage(p)}
                    />
                  </Box>
                )}
              </>
            )}
          </Box>
        )}

        {/* Config Audit Tab */}
        {currentTab === 2 && (
          <Box sx={{ p: 2 }}>
            {configAuditLoading ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                <CircularProgress />
              </Box>
            ) : configAuditError ? (
              <Typography color="error">{configAuditError}</Typography>
            ) : (
              <>
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                        <TableCell>Date</TableCell>
                        <TableCell>Config Key</TableCell>
                        <TableCell>Old Value</TableCell>
                        <TableCell>New Value</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {configAudits.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={4} align="center" sx={{ py: 3 }}>
                            No config changes found
                          </TableCell>
                        </TableRow>
                      ) : (
                        configAudits.map((log, idx) => (
                          <TableRow key={idx} hover>
                            <TableCell>{formatDate(log.changed_at)}</TableCell>
                            <TableCell>{log.config_key}</TableCell>
                            <TableCell>
                              <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                                {log.old_value}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'green' }}>
                                {log.new_value}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </Box>
                {configPagination.total > 0 && (
                  <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                    <Pagination
                      page={page}
                      count={Math.ceil(configPagination.total / limit)}
                      onChange={(e, p) => setPage(p)}
                    />
                  </Box>
                )}
              </>
            )}
          </Box>
        )}
      </Paper>
    </Box>
  );
};

export default AuditViewer;
