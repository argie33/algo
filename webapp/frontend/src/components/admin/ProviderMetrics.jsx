import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Grid,
  Box,
  Chip,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Alert
} from '@mui/material';
import {
  Speed as SpeedIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Settings as SettingsIcon,
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  Refresh as RefreshIcon,
  Warning as WarningIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon
} from '@mui/icons-material';

const ProviderMetrics = ({ providersData, onProviderUpdate, onRefresh }) => {
  const [settingsDialog, setSettingsDialog] = useState({ open: false, provider: null });
  const [providers, setProviders] = useState(providersData || {});

  useEffect(() => {
    setProviders(providersData || {});
  }, [providersData]);

  const getStatusIcon = (status) => {
    switch (status) {
      case 'operational':
        return <CheckIcon color="success" />;
      case 'warning':
        return <WarningIcon color="warning" />;
      case 'error':
        return <ErrorIcon color="error" />;
      default:
        return <StopIcon color="disabled" />;
    }
  };

  const getLatencyColor = (latency) => {
    if (latency < 50) return 'success';
    if (latency < 100) return 'warning';
    return 'error';
  };

  const handleProviderToggle = async (providerId, enabled) => {
    try {
      // Mock API call - replace with actual endpoint
      const response = await fetch(`/api/liveData/providers/${providerId}/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled })
      });

      if (response.ok) {
        setProviders(prev => ({
          ...prev,
          [providerId]: {
            ...prev[providerId],
            status: enabled ? 'operational' : 'disconnected'
          }
        }));
        onProviderUpdate?.(providerId, { enabled });
      }
    } catch (error) {
      console.error('Failed to toggle provider:', error);
    }
  };

  const handleSettingsOpen = (providerId) => {
    setSettingsDialog({ open: true, provider: providerId });
  };

  const handleSettingsClose = () => {
    setSettingsDialog({ open: false, provider: null });
  };

  const handleSettingsSave = async (settings) => {
    try {
      // Mock API call - replace with actual endpoint
      const response = await fetch(`/api/liveData/providers/${settingsDialog.provider}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });

      if (response.ok) {
        onProviderUpdate?.(settingsDialog.provider, settings);
        handleSettingsClose();
      }
    } catch (error) {
      console.error('Failed to update provider settings:', error);
    }
  };

  return (
    <Box>
      {/* Provider Overview Cards */}
      <Grid container spacing={3} mb={3}>
        {Object.entries(providers).map(([providerId, provider]) => (
          <Grid item xs={12} md={4} key={providerId}>
            <Card elevation={2}>
              <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="start" mb={2}>
                  <Box display="flex" alignItems="center" gap={1}>
                    {getStatusIcon(provider.status)}
                    <Typography variant="h6" fontWeight="bold">
                      {provider.name}
                    </Typography>
                  </Box>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={provider.status === 'operational'}
                        onChange={(e) => handleProviderToggle(providerId, e.target.checked)}
                        size="small"
                      />
                    }
                    label=""
                  />
                </Box>

                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Connections
                    </Typography>
                    <Typography variant="h5">
                      {provider.connections}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Symbols
                    </Typography>
                    <Typography variant="h5">
                      {provider.symbols}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Latency
                    </Typography>
                    <Box display="flex" alignItems="center" gap={1}>
                      <Typography variant="h6" color={`${getLatencyColor(provider.latency)}.main`}>
                        {provider.latency.toFixed(0)}ms
                      </Typography>
                      {provider.latency < 50 ? <TrendingUpIcon fontSize="small" color="success" /> : 
                       provider.latency > 100 ? <TrendingDownIcon fontSize="small" color="error" /> : null}
                    </Box>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Success Rate
                    </Typography>
                    <Typography 
                      variant="h6" 
                      color={provider.successRate > 95 ? 'success.main' : 'error.main'}
                    >
                      {provider.successRate.toFixed(1)}%
                    </Typography>
                  </Grid>
                </Grid>

                <Box mt={2}>
                  <Typography variant="body2" color="textSecondary" gutterBottom>
                    Daily Cost: ${provider.costToday.toFixed(2)}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={provider.rateLimitUsage || 0}
                    color={provider.rateLimitUsage > 80 ? 'error' : 'primary'}
                  />
                  <Typography variant="caption" color="textSecondary">
                    Rate Limit Usage: {(provider.rateLimitUsage || 0).toFixed(1)}%
                  </Typography>
                </Box>

                <Box display="flex" justifyContent="flex-end" mt={2} gap={1}>
                  <IconButton
                    size="small"
                    onClick={() => handleSettingsOpen(providerId)}
                    disabled={provider.status === 'disconnected'}
                  >
                    <SettingsIcon />
                  </IconButton>
                  <IconButton
                    size="small"
                    onClick={onRefresh}
                  >
                    <RefreshIcon />
                  </IconButton>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Detailed Provider Table */}
      <Card elevation={2}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6" fontWeight="bold">
              Provider Performance Details
            </Typography>
            <Button
              startIcon={<RefreshIcon />}
              onClick={onRefresh}
              variant="outlined"
              size="small"
            >
              Refresh All
            </Button>
          </Box>

          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Provider</TableCell>
                  <TableCell align="center">Status</TableCell>
                  <TableCell align="right">Connections</TableCell>
                  <TableCell align="right">Symbols</TableCell>
                  <TableCell align="right">Requests Today</TableCell>
                  <TableCell align="right">Latency (ms)</TableCell>
                  <TableCell align="right">Success Rate</TableCell>
                  <TableCell align="right">Cost Today</TableCell>
                  <TableCell align="right">Uptime</TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {Object.entries(providers).map(([providerId, provider]) => (
                  <TableRow key={providerId}>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        {getStatusIcon(provider.status)}
                        <Typography variant="body2" fontWeight="medium">
                          {provider.name}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={provider.status}
                        size="small"
                        color={
                          provider.status === 'operational' ? 'success' :
                          provider.status === 'warning' ? 'warning' : 'error'
                        }
                      />
                    </TableCell>
                    <TableCell align="right">{provider.connections}</TableCell>
                    <TableCell align="right">{provider.symbols}</TableCell>
                    <TableCell align="right">{provider.requestsToday.toLocaleString()}</TableCell>
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        color={`${getLatencyColor(provider.latency)}.main`}
                        fontWeight="medium"
                      >
                        {provider.latency.toFixed(0)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        color={provider.successRate > 95 ? 'success.main' : 'error.main'}
                        fontWeight="medium"
                      >
                        {provider.successRate.toFixed(1)}%
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" fontWeight="medium">
                        ${provider.costToday.toFixed(2)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {((provider.uptime || 0) / 3600000).toFixed(1)}h
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title="Provider Settings">
                        <IconButton
                          size="small"
                          onClick={() => handleSettingsOpen(providerId)}
                        >
                          <SettingsIcon />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* Provider Settings Dialog */}
      <Dialog
        open={settingsDialog.open}
        onClose={handleSettingsClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          Provider Settings - {settingsDialog.provider && providers[settingsDialog.provider]?.name}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Rate Limit (requests/minute)"
                  type="number"
                  defaultValue={200}
                  variant="outlined"
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Max Concurrent Connections"
                  type="number"
                  defaultValue={5}
                  variant="outlined"
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Cost Per Request ($)"
                  type="number"
                  step="0.001"
                  defaultValue={0.004}
                  variant="outlined"
                />
              </Grid>
              <Grid item xs={12}>
                <Alert severity="info">
                  Changes will take effect immediately and may briefly interrupt active connections.
                </Alert>
              </Grid>
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleSettingsClose}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => handleSettingsSave({})}
          >
            Save Settings
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ProviderMetrics;