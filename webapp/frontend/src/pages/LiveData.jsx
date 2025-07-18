import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  Switch,
  FormControlLabel,
  Button,
  Chip,
  Alert,
  LinearProgress,
  IconButton,
  Tooltip,
  CircularProgress,
  Stack
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Stop,
  Settings,
  Analytics,
  Refresh,
  ShowChart,
  Assessment,
  Warning,
  CheckCircle,
  Error,
  Info
} from '@mui/icons-material';

const LiveData = () => {
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  // Mock data for demonstration
  const mockData = [
    { symbol: 'AAPL', price: 175.43, change: 2.1, changePercent: 1.21 },
    { symbol: 'GOOGL', price: 2421.33, change: -15.20, changePercent: -0.62 },
    { symbol: 'MSFT', price: 377.85, change: 4.75, changePercent: 1.27 },
    { symbol: 'TSLA', price: 248.42, change: -8.33, changePercent: -3.24 }
  ];

  useEffect(() => {
    // Simulate connection status
    if (isStreaming) {
      setConnectionStatus('connected');
      setData(mockData);
    } else {
      setConnectionStatus('disconnected');
      setData([]);
    }
  }, [isStreaming]);

  const toggleStreaming = () => {
    setLoading(true);
    setTimeout(() => {
      setIsStreaming(!isStreaming);
      setLoading(false);
    }, 1000);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'success';
      case 'connecting': return 'warning';
      default: return 'error';
    }
  };

  const getChangeIcon = (change) => {
    return change >= 0 ? <TrendingUp color="success" /> : <TrendingDown color="error" />;
  };

  const getChangeColor = (change) => {
    return change >= 0 ? 'success.main' : 'error.main';
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Live Market Data
      </Typography>
      
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Real-time market data streaming with live price updates and market analytics.
      </Typography>

      {/* Connection Status */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between">
          <Box>
            <Typography variant="h6">Connection Status</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip 
                label={connectionStatus.toUpperCase()} 
                color={getStatusColor(connectionStatus)}
                size="small"
              />
              {isStreaming && (
                <Chip label="LIVE" color="success" size="small" />
              )}
            </Stack>
          </Box>
          
          <Stack direction="row" spacing={1}>
            <Button
              variant={isStreaming ? "outlined" : "contained"}
              color={isStreaming ? "error" : "success"}
              onClick={toggleStreaming}
              disabled={loading}
              startIcon={loading ? <CircularProgress size={16} /> : (isStreaming ? <Stop /> : <PlayArrow />)}
            >
              {loading ? 'Connecting...' : (isStreaming ? 'Stop Stream' : 'Start Stream')}
            </Button>
            
            <Tooltip title="Refresh Data">
              <IconButton>
                <Refresh />
              </IconButton>
            </Tooltip>
            
            <Tooltip title="Settings">
              <IconButton>
                <Settings />
              </IconButton>
            </Tooltip>
          </Stack>
        </Stack>
      </Paper>

      {/* Market Data Grid */}
      {isStreaming ? (
        <Grid container spacing={3}>
          {data.map((stock) => (
            <Grid item xs={12} sm={6} md={3} key={stock.symbol}>
              <Card>
                <CardContent>
                  <Stack spacing={2}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                      <Typography variant="h6" component="div">
                        {stock.symbol}
                      </Typography>
                      {getChangeIcon(stock.change)}
                    </Stack>
                    
                    <Typography variant="h4" component="div">
                      ${stock.price.toFixed(2)}
                    </Typography>
                    
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography 
                        variant="body2" 
                        sx={{ color: getChangeColor(stock.change) }}
                      >
                        {stock.change >= 0 ? '+' : ''}${stock.change.toFixed(2)}
                      </Typography>
                      <Typography 
                        variant="body2" 
                        sx={{ color: getChangeColor(stock.change) }}
                      >
                        ({stock.changePercent >= 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%)
                      </Typography>
                    </Stack>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      ) : (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <ShowChart sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h6" color="text.secondary">
            Live data streaming is stopped
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Click "Start Stream" to begin receiving real-time market data
          </Typography>
          <Button 
            variant="contained" 
            onClick={toggleStreaming}
            startIcon={<PlayArrow />}
          >
            Start Live Stream
          </Button>
        </Paper>
      )}

      {/* Quick Stats */}
      <Paper sx={{ p: 2, mt: 3 }}>
        <Typography variant="h6" gutterBottom>
          Stream Statistics
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={6} md={3}>
            <Stack spacing={1}>
              <Typography variant="body2" color="text.secondary">
                Active Connections
              </Typography>
              <Typography variant="h6">
                {isStreaming ? '1' : '0'}
              </Typography>
            </Stack>
          </Grid>
          <Grid item xs={6} md={3}>
            <Stack spacing={1}>
              <Typography variant="body2" color="text.secondary">
                Data Points
              </Typography>
              <Typography variant="h6">
                {data.length}
              </Typography>
            </Stack>
          </Grid>
          <Grid item xs={6} md={3}>
            <Stack spacing={1}>
              <Typography variant="body2" color="text.secondary">
                Update Rate
              </Typography>
              <Typography variant="h6">
                {isStreaming ? '1s' : '0s'}
              </Typography>
            </Stack>
          </Grid>
          <Grid item xs={6} md={3}>
            <Stack spacing={1}>
              <Typography variant="body2" color="text.secondary">
                Status
              </Typography>
              <Typography variant="h6" sx={{ color: getChangeColor(isStreaming ? 1 : -1) }}>
                {isStreaming ? 'LIVE' : 'STOPPED'}
              </Typography>
            </Stack>
          </Grid>
        </Grid>
      </Paper>

      {/* Info Alert */}
      <Alert severity="info" sx={{ mt: 3 }}>
        <Typography variant="body2">
          This is a simplified version of the Live Data page. Real-time streaming 
          capabilities include WebSocket connections, multiple data sources, and 
          advanced charting features.
        </Typography>
      </Alert>
    </Box>
  );
};

export default LiveData;