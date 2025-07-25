import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Chip,
  CircularProgress,
  IconButton,
  Tooltip,
  Alert,
  Stack,
  LinearProgress
} from '@mui/material';
import {
  CloudSync,
  Check,
  Error,
  Refresh,
  Schedule,
  TrendingUp
} from '@mui/icons-material';
import { initializeApi } from '../../services/api';

const PortfolioSyncStatus = ({ userId, onSyncComplete, compact = false }) => {
  const [syncStatus, setSyncStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchSyncStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const api = await initializeApi();
      const response = await api.get('/api/portfolio/sync-status');
      
      if (response.data && response.data.success) {
        setSyncStatus(response.data.syncStatus);
        setLastUpdated(new Date().toLocaleTimeString());
      }
    } catch (err) {
      console.error('Failed to fetch sync status:', err);
      setError(err.response?.data?.error || 'Failed to fetch sync status');
    } finally {
      setLoading(false);
    }
  };

  const triggerSync = async (force = false) => {
    try {
      setLoading(true);
      const api = await initializeApi();
      await api.get(`/api/portfolio/holdings?force=${force}`);
      
      // Refresh sync status after triggering sync
      setTimeout(() => {
        fetchSyncStatus();
        if (onSyncComplete) onSyncComplete();
      }, 1000);
      
    } catch (err) {
      console.error('Failed to trigger sync:', err);
      setError('Failed to trigger sync');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSyncStatus();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchSyncStatus, 30000);
    return () => clearInterval(interval);
  }, [userId]);

  const getSyncStatusColor = (status) => {
    switch (status?.status) {
      case 'synced':
      case 'completed':
        return 'success';
      case 'syncing':
      case 'in_progress':
        return 'info';
      case 'failed':
      case 'error':
        return 'error';
      case 'never_synced':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getSyncStatusIcon = (status) => {
    switch (status?.status) {
      case 'synced':
      case 'completed':
        return <Check />;
      case 'syncing':
      case 'in_progress':
        return <CircularProgress size={16} />;
      case 'failed':
      case 'error':
        return <Error />;
      case 'never_synced':
        return <Schedule />;
      default:
        return <CloudSync />;
    }
  };

  const formatDuration = (ms) => {
    if (!ms) return 'N/A';
    return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
  };

  if (compact) {
    return (
      <Box display="flex" alignItems="center" gap={1}>
        <Chip
          icon={loading ? <CircularProgress size={16} /> : getSyncStatusIcon(syncStatus)}
          label={loading ? 'Loading...' : (syncStatus?.status || 'Unknown')}
          color={getSyncStatusColor(syncStatus)}
          size="small"
        />
        <Tooltip title="Force refresh from broker">
          <IconButton size="small" onClick={() => triggerSync(true)} disabled={loading}>
            <Refresh />
          </IconButton>
        </Tooltip>
      </Box>
    );
  }

  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Box display="flex" justifyContent="between" alignItems="center" mb={2}>
          <Typography variant="h6" display="flex" alignItems="center" gap={1}>
            <CloudSync />
            Portfolio Sync Status
          </Typography>
          <Box display="flex" gap={1}>
            <Tooltip title="Refresh status">
              <IconButton onClick={fetchSyncStatus} disabled={loading}>
                <Refresh />
              </IconButton>
            </Tooltip>
            <Tooltip title="Force sync from broker">
              <IconButton onClick={() => triggerSync(true)} disabled={loading}>
                <TrendingUp />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {loading && !syncStatus ? (
          <Box display="flex" alignItems="center" gap={2}>
            <CircularProgress size={20} />
            <Typography>Loading sync status...</Typography>
          </Box>
        ) : (
          <Stack spacing={2}>
            <Box display="flex" justifyContent="between" alignItems="center">
              <Box display="flex" alignItems="center" gap={1}>
                <Chip
                  icon={getSyncStatusIcon(syncStatus)}
                  label={syncStatus?.status || 'Unknown'}
                  color={getSyncStatusColor(syncStatus)}
                />
                <Typography variant="body2" color="text.secondary">
                  {syncStatus?.lastSyncAt 
                    ? `Last sync: ${new Date(syncStatus.lastSyncAt).toLocaleString()}`
                    : 'Never synced'
                  }
                </Typography>
              </Box>
              
              {lastUpdated && (
                <Typography variant="caption" color="text.secondary">
                  Updated: {lastUpdated}
                </Typography>
              )}
            </Box>

            {syncStatus?.duration && (
              <Box>
                <Typography variant="body2" color="text.secondary">
                  Last sync duration: {formatDuration(syncStatus.duration)}
                </Typography>
              </Box>
            )}

            {syncStatus?.recordsProcessed && (
              <Box>
                <Typography variant="body2" color="text.secondary">
                  Records processed: {syncStatus.recordsProcessed}
                </Typography>
              </Box>
            )}

            {syncStatus?.status === 'syncing' && syncStatus?.progress && (
              <Box>
                <Typography variant="body2" gutterBottom>
                  Sync Progress: {syncStatus.progress}%
                </Typography>
                <LinearProgress variant="determinate" value={syncStatus.progress} />
              </Box>
            )}

            {syncStatus?.error && (
              <Alert severity="error">
                Sync Error: {syncStatus.error}
              </Alert>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
};

export default PortfolioSyncStatus;