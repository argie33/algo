import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  LinearProgress,
  Chip,
  CircularProgress,
  Tooltip,
  Alert,
  IconButton,
  Badge
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  Psychology,
  Refresh,
  Update,
  Speed,
  SignalCellular4Bar,
  SignalCellularNodata
} from '@mui/icons-material';
import realTimeNewsService from '../services/realTimeNewsService.js';

const RealTimeSentimentScore = ({ 
  symbol, 
  showDetails = true, 
  size = 'medium',
  autoRefresh = true,
  refreshInterval = 30000
}) => {
  const [sentiment, setSentiment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [realtimeUpdates, setRealtimeUpdates] = useState(0);

  // Subscribe to real-time sentiment updates
  useEffect(() => {
    if (!symbol) {
      setLoading(false);
      return;
    }

    setLoading(true);
    let subscriptionId = null;

    const handleSentimentUpdate = (sentimentData) => {
      setSentiment(sentimentData);
      setLastUpdate(new Date());
      setRealtimeUpdates(prev => prev + 1);
      setConnectionStatus('connected');
      setLoading(false);
    };

    const handleConnectionError = () => {
      setConnectionStatus('error');
    };

    // Subscribe to sentiment updates for this symbol
    subscriptionId = realTimeNewsService.subscribeToSentiment(symbol, handleSentimentUpdate);

    // Initial fetch
    const fetchInitialSentiment = async () => {
      try {
        const existingSentiment = realTimeNewsService.getLatestSentiment(symbol);
        if (existingSentiment) {
          handleSentimentUpdate(existingSentiment);
        } else {
          // Fetch from API if no cached data
          const sentimentData = await realTimeNewsService.fetchNewsSentiment(symbol);
          if (sentimentData) {
            handleSentimentUpdate(sentimentData);
          }
        }
      } catch (error) {
        console.error('Failed to fetch initial sentiment:', error);
        handleConnectionError();
        setLoading(false);
      }
    };

    fetchInitialSentiment();

    return () => {
      if (subscriptionId) {
        realTimeNewsService.unsubscribeFromSentiment(symbol, subscriptionId);
      }
    };
  }, [symbol]);

  // Auto-refresh functionality
  useEffect(() => {
    if (!autoRefresh || !symbol) return;

    const interval = setInterval(async () => {
      try {
        const sentimentData = await realTimeNewsService.fetchNewsSentiment(symbol);
        if (sentimentData) {
          setSentiment(sentimentData);
          setLastUpdate(new Date());
        }
      } catch (error) {
        console.error('Auto-refresh failed:', error);
        setConnectionStatus('error');
      }
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [symbol, autoRefresh, refreshInterval]);

  const refreshSentiment = useCallback(async () => {
    if (!symbol) return;
    
    setLoading(true);
    try {
      const sentimentData = await realTimeNewsService.fetchNewsSentiment(symbol);
      if (sentimentData) {
        setSentiment(sentimentData);
        setLastUpdate(new Date());
        setConnectionStatus('connected');
      }
    } catch (error) {
      console.error('Manual refresh failed:', error);
      setConnectionStatus('error');
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  // Calculate display values
  const displayValues = useMemo(() => {
    if (!sentiment) {
      return {
        score: 0,
        label: 'No Data',
        color: 'text.secondary',
        icon: <SignalCellularNodata />,
        confidence: 0,
        trend: 'flat'
      };
    }

    const score = sentiment.score || 0;
    const confidence = sentiment.confidence || 0;
    
    let label = 'Neutral';
    let color = 'text.secondary';
    let icon = <TrendingFlat />;
    
    if (score >= 0.6) {
      label = 'Bullish';
      color = 'success.main';
      icon = <TrendingUp />;
    } else if (score <= 0.4) {
      label = 'Bearish';
      color = 'error.main';
      icon = <TrendingDown />;
    }

    return {
      score: Math.round(score * 100),
      label,
      color,
      icon,
      confidence: Math.round(confidence * 100),
      trend: sentiment.trend || 'flat'
    };
  }, [sentiment]);

  const getSizeStyles = () => {
    switch (size) {
      case 'small':
        return {
          padding: 1,
          fontSize: '0.875rem',
          scoreSize: 'h6'
        };
      case 'large':
        return {
          padding: 3,
          fontSize: '1.125rem',
          scoreSize: 'h3'
        };
      default:
        return {
          padding: 2,
          fontSize: '1rem',
          scoreSize: 'h4'
        };
    }
  };

  const styles = getSizeStyles();

  const getConnectionIcon = () => {
    switch (connectionStatus) {
      case 'connected':
        return <SignalCellular4Bar color="success" />;
      case 'error':
        return <SignalCellularNodata color="error" />;
      default:
        return <Speed color="action" />;
    }
  };

  if (loading && !sentiment) {
    return (
      <Card>
        <CardContent sx={{ padding: styles.padding }}>
          <Box display="flex" alignItems="center" justifyContent="center" gap={2}>
            <CircularProgress size={24} />
            <Typography>Loading sentiment...</Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (!sentiment && !loading) {
    return (
      <Card>
        <CardContent sx={{ padding: styles.padding }}>
          <Alert severity="info">
            No sentiment data available for {symbol}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent sx={{ padding: styles.padding }}>
        {/* Header */}
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <Psychology color="primary" />
            <Typography variant="h6" component="h3">
              Sentiment Score
              {symbol && ` - ${symbol}`}
            </Typography>
            {sentiment?.isRealTime && (
              <Badge badgeContent={realtimeUpdates} color="success">
                <Chip label="LIVE" color="success" size="small" />
              </Badge>
            )}
          </Box>
          
          <Box display="flex" alignItems="center" gap={1}>
            <Tooltip title={`Connection: ${connectionStatus}`}>
              {getConnectionIcon()}
            </Tooltip>
            <IconButton 
              size="small" 
              onClick={refreshSentiment}
              disabled={loading}
            >
              <Refresh />
            </IconButton>
          </Box>
        </Box>

        {/* Main Score Display */}
        <Box display="flex" alignItems="center" justifyContent="center" mb={2}>
          <Box textAlign="center">
            <Box display="flex" alignItems="center" justifyContent="center" gap={1} mb={1}>
              {displayValues.icon}
              <Typography 
                variant={styles.scoreSize}
                color={displayValues.color}
                fontWeight="bold"
              >
                {displayValues.score}
              </Typography>
            </Box>
            
            <Typography variant="body2" color="text.secondary">
              {displayValues.label}
            </Typography>
            
            {/* Progress Bar */}
            <LinearProgress
              variant="determinate"
              value={displayValues.score}
              color={
                displayValues.score >= 60 ? 'success' : 
                displayValues.score <= 40 ? 'error' : 'warning'
              }
              sx={{ 
                mt: 1, 
                height: 8, 
                borderRadius: 4,
                backgroundColor: 'rgba(0,0,0,0.1)'
              }}
            />
          </Box>
        </Box>

        {/* Details */}
        {showDetails && (
          <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography variant="body2" color="text.secondary">
                Confidence
              </Typography>
              <Typography variant="body2" fontWeight="medium">
                {displayValues.confidence}%
              </Typography>
            </Box>

            {sentiment?.articles && (
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                <Typography variant="body2" color="text.secondary">
                  Articles Analyzed
                </Typography>
                <Typography variant="body2" fontWeight="medium">
                  {sentiment.articles.length}
                </Typography>
              </Box>
            )}

            {lastUpdate && (
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                <Typography variant="body2" color="text.secondary">
                  Last Update
                </Typography>
                <Typography variant="body2" fontWeight="medium">
                  {lastUpdate.toLocaleTimeString()}
                </Typography>
              </Box>
            )}

            {/* Trend Indicator */}
            {sentiment?.trend && sentiment.trend !== 'flat' && (
              <Box display="flex" alignItems="center" gap={1} mt={2}>
                <Update color="action" />
                <Typography variant="body2" color="text.secondary">
                  Trend: 
                </Typography>
                <Chip 
                  label={sentiment.trend}
                  color={sentiment.trend === 'improving' ? 'success' : 'error'}
                  size="small"
                  variant="outlined"
                />
              </Box>
            )}

            {/* Source Summary */}
            {sentiment?.sources && sentiment.sources.length > 0 && (
              <Box mt={2}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Top Sources
                </Typography>
                <Box display="flex" gap={0.5} flexWrap="wrap">
                  {sentiment.sources.slice(0, 3).map((source, index) => (
                    <Chip
                      key={index}
                      label={source.source || 'Unknown'}
                      size="small"
                      variant="outlined"
                    />
                  ))}
                </Box>
              </Box>
            )}
          </Box>
        )}

        {/* Connection Status Alert */}
        {connectionStatus === 'error' && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            <Typography variant="body2">
              Real-time updates unavailable. Using cached data.
            </Typography>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
};

export default RealTimeSentimentScore;