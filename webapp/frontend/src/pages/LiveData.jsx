import React, { useState, useEffect, useRef } from 'react';
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
  Stack,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider
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
  Info,
  Add,
  Remove,
  Timeline,
  MonetizationOn
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { getApiConfig } from '../services/api';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

const LiveData = () => {
  const { user, isAuthenticated } = useAuth();
  const { apiUrl } = getApiConfig();
  const wsRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  
  // State management
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [subscriptions, setSubscriptions] = useState([]);
  const [availableFeeds, setAvailableFeeds] = useState(null);
  const [newSymbol, setNewSymbol] = useState('');
  const [selectedDataType, setSelectedDataType] = useState('quotes');
  const [selectedFrequency, setSelectedFrequency] = useState('1Min');
  const [connectionStats, setConnectionStats] = useState({
    messagesReceived: 0,
    lastUpdate: null,
    latency: 0,
    errors: 0
  });
  const [marketData, setMarketData] = useState(new Map());
  
  // Get WebSocket URL from config or CloudFormation outputs
  const getWebSocketUrl = () => {
    // Try to get from runtime config first
    if (window.__CONFIG__?.WS_URL) {
      return window.__CONFIG__.WS_URL;
    }
    
    // Try to get from CloudFormation exports (would need to be configured)
    if (window.__CONFIG__?.ALPACA_WEBSOCKET_ENDPOINT) {
      return window.__CONFIG__.ALPACA_WEBSOCKET_ENDPOINT;
    }
    
    // Default to expected CloudFormation export format
    return 'wss://YOUR_WEBSOCKET_ID.execute-api.us-east-1.amazonaws.com/dev';
  };
  
  const wsUrl = getWebSocketUrl();

  // Initialize WebSocket connection
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);
  
  // Connect to WebSocket
  const connectWebSocket = async () => {
    try {
      setLoading(true);
      setConnectionStatus('connecting');
      
      const userId = user?.sub || 'anonymous';
      const fullWsUrl = `${wsUrl}?userId=${userId}`;
      
      console.log('🔌 Connecting to WebSocket:', fullWsUrl);
      
      wsRef.current = new WebSocket(fullWsUrl);
      
      wsRef.current.onopen = () => {
        console.log('✅ WebSocket connected');
        setConnectionStatus('connected');
        setIsStreaming(true);
        setLoading(false);
        reconnectAttempts.current = 0;
        
        // Request available feeds
        sendMessage({
          action: 'get_available_feeds'
        });
      };
      
      wsRef.current.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          handleWebSocketMessage(message);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
          setConnectionStats(prev => ({ ...prev, errors: prev.errors + 1 }));
        }
      };
      
      wsRef.current.onclose = (event) => {
        console.log('🔌 WebSocket disconnected:', event.code, event.reason);
        setConnectionStatus('disconnected');
        setIsStreaming(false);
        setLoading(false);
        
        // Attempt to reconnect if not a manual disconnect
        if (event.code !== 1000 && reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++;
          console.log(`🔄 Attempting to reconnect (${reconnectAttempts.current}/${maxReconnectAttempts})`);
          setTimeout(() => {
            connectWebSocket();
          }, 3000 * reconnectAttempts.current);
        }
      };
      
      wsRef.current.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        setConnectionStatus('error');
        setConnectionStats(prev => ({ ...prev, errors: prev.errors + 1 }));
      };
      
    } catch (error) {
      console.error('❌ Failed to connect WebSocket:', error);
      setConnectionStatus('error');
      setLoading(false);
    }
  };
  
  // Disconnect WebSocket
  const disconnectWebSocket = () => {
    if (wsRef.current) {
      wsRef.current.close(1000, 'Manual disconnect');
      wsRef.current = null;
    }
    setConnectionStatus('disconnected');
    setIsStreaming(false);
    setSubscriptions([]);
    setMarketData(new Map());
    setData([]);
  };
  
  // Send message to WebSocket
  const sendMessage = (message) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
      console.log('📤 Sent message:', message);
    } else {
      console.warn('⚠️ WebSocket not connected, cannot send message');
    }
  };
  
  // Handle WebSocket messages
  const handleWebSocketMessage = (message) => {
    console.log('📥 Received message:', message);
    
    setConnectionStats(prev => ({
      ...prev,
      messagesReceived: prev.messagesReceived + 1,
      lastUpdate: new Date()
    }));
    
    switch (message.action) {
      case 'available_feeds':
        setAvailableFeeds(message.feeds);
        break;
        
      case 'subscribed':
        setSubscriptions(prev => [...prev, {
          id: message.subscriptionId,
          symbols: message.symbols,
          dataType: message.dataType,
          frequency: message.frequency
        }]);
        break;
        
      case 'subscriptions_list':
        setSubscriptions(message.subscriptions);
        break;
        
      case 'pong':
        console.log('🏓 Pong received');
        break;
        
      case 'market_data':
      case 'data_update':
        handleMarketDataUpdate(message);
        break;
        
      default:
        console.log('📨 Unknown message type:', message.action);
    }
  };
  
  // Handle market data updates
  const handleMarketDataUpdate = (message) => {
    if (message.type === 'market_data') {
      const { symbol, data: symbolData } = message;
      
      setMarketData(prev => {
        const newData = new Map(prev);
        newData.set(symbol, {
          ...symbolData,
          timestamp: message.timestamp,
          symbol: symbol
        });
        return newData;
      });
      
      // Update the display data array
      setData(prev => {
        const existingIndex = prev.findIndex(item => item.symbol === symbol);
        const newItem = {
          symbol: symbol,
          price: symbolData.price || symbolData.ask || symbolData.bid,
          change: symbolData.change || 0,
          changePercent: symbolData.changePercent || 0,
          bid: symbolData.bid,
          ask: symbolData.ask,
          volume: symbolData.volume,
          timestamp: symbolData.timestamp
        };
        
        if (existingIndex >= 0) {
          const newData = [...prev];
          newData[existingIndex] = newItem;
          return newData;
        } else {
          return [...prev, newItem];
        }
      });
    }
  };
  
  // Subscribe to symbols
  const subscribeToSymbol = () => {
    if (!newSymbol.trim()) return;
    
    const symbols = [newSymbol.toUpperCase()];
    
    sendMessage({
      action: 'subscribe',
      symbols: symbols,
      dataType: selectedDataType,
      frequency: selectedFrequency
    });
    
    setNewSymbol('');
  };
  
  // Unsubscribe from symbols
  const unsubscribeFromSymbol = (subscriptionId) => {
    sendMessage({
      action: 'unsubscribe',
      subscriptionId: subscriptionId
    });
    
    setSubscriptions(prev => prev.filter(sub => sub.id !== subscriptionId));
  };
  
  // List current subscriptions
  const listSubscriptions = () => {
    sendMessage({
      action: 'list_subscriptions'
    });
  };
  
  // Send ping
  const sendPing = () => {
    sendMessage({
      action: 'ping'
    });
  };

  const toggleStreaming = () => {
    if (isStreaming) {
      disconnectWebSocket();
    } else {
      connectWebSocket();
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'success';
      case 'connecting': return 'warning';
      case 'error': return 'error';
      default: return 'default';
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
      {/* API Key Status */}
      <Box sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          showSetupDialog={true}
          requiredProviders={['alpaca']}
        />
      </Box>
      
      <Typography variant="h4" component="h1" gutterBottom>
        Live Market Data - WebSocket Integration
      </Typography>
      
      <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
        Real-time market data streaming via WebSocket infrastructure with Alpaca integration.
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
              {loading ? 'Connecting...' : (isStreaming ? 'Disconnect' : 'Connect WebSocket')}
            </Button>
            
            <Tooltip title="List Subscriptions">
              <IconButton onClick={listSubscriptions} disabled={!isStreaming}>
                <ShowChart />
              </IconButton>
            </Tooltip>
            
            <Tooltip title="Send Ping">
              <IconButton onClick={sendPing} disabled={!isStreaming}>
                <Timeline />
              </IconButton>
            </Tooltip>
            
            <Tooltip title="Refresh Data">
              <IconButton>
                <Refresh />
              </IconButton>
            </Tooltip>
          </Stack>
        </Stack>
      </Paper>

      {/* Subscription Management */}
      {isStreaming && (
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Subscribe to Symbols
              </Typography>
              <Stack spacing={2}>
                <TextField
                  label="Symbol"
                  value={newSymbol}
                  onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                  placeholder="e.g., AAPL"
                  size="small"
                  onKeyPress={(e) => e.key === 'Enter' && subscribeToSymbol()}
                />
                <Stack direction="row" spacing={2}>
                  <FormControl size="small" sx={{ minWidth: 120 }}>
                    <InputLabel>Data Type</InputLabel>
                    <Select
                      value={selectedDataType}
                      label="Data Type"
                      onChange={(e) => setSelectedDataType(e.target.value)}
                    >
                      <MenuItem value="quotes">Quotes</MenuItem>
                      <MenuItem value="trades">Trades</MenuItem>
                      <MenuItem value="bars">Bars</MenuItem>
                      <MenuItem value="news">News</MenuItem>
                      <MenuItem value="crypto">Crypto</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl size="small" sx={{ minWidth: 120 }}>
                    <InputLabel>Frequency</InputLabel>
                    <Select
                      value={selectedFrequency}
                      label="Frequency"
                      onChange={(e) => setSelectedFrequency(e.target.value)}
                    >
                      <MenuItem value="1Min">1 Min</MenuItem>
                      <MenuItem value="5Min">5 Min</MenuItem>
                      <MenuItem value="15Min">15 Min</MenuItem>
                      <MenuItem value="1Hour">1 Hour</MenuItem>
                      <MenuItem value="1Day">1 Day</MenuItem>
                    </Select>
                  </FormControl>
                </Stack>
                <Button
                  variant="contained"
                  onClick={subscribeToSymbol}
                  disabled={!newSymbol.trim()}
                  startIcon={<Add />}
                >
                  Subscribe
                </Button>
              </Stack>
            </Paper>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>
                Active Subscriptions ({subscriptions.length})
              </Typography>
              <List dense>
                {subscriptions.map((sub) => (
                  <ListItem key={sub.id}>
                    <ListItemIcon>
                      <MonetizationOn />
                    </ListItemIcon>
                    <ListItemText
                      primary={sub.symbols?.join(', ')}
                      secondary={`${sub.dataType} - ${sub.frequency}`}
                    />
                    <IconButton 
                      onClick={() => unsubscribeFromSymbol(sub.id)}
                      color="error"
                      size="small"
                    >
                      <Remove />
                    </IconButton>
                  </ListItem>
                ))}
                {subscriptions.length === 0 && (
                  <ListItem>
                    <ListItemText primary="No active subscriptions" />
                  </ListItem>
                )}
              </List>
            </Paper>
          </Grid>
        </Grid>
      )}
      
      {/* Connection Stats */}
      {isStreaming && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Connection Statistics
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={3}>
              <Typography variant="body2" color="text.secondary">Messages Received</Typography>
              <Typography variant="h6">{connectionStats.messagesReceived}</Typography>
            </Grid>
            <Grid item xs={3}>
              <Typography variant="body2" color="text.secondary">Last Update</Typography>
              <Typography variant="body2">
                {connectionStats.lastUpdate ? connectionStats.lastUpdate.toLocaleTimeString() : 'None'}
              </Typography>
            </Grid>
            <Grid item xs={3}>
              <Typography variant="body2" color="text.secondary">Errors</Typography>
              <Typography variant="h6" color={connectionStats.errors > 0 ? 'error' : 'inherit'}>
                {connectionStats.errors}
              </Typography>
            </Grid>
            <Grid item xs={3}>
              <Typography variant="body2" color="text.secondary">WebSocket URL</Typography>
              <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                {wsUrl}
              </Typography>
            </Grid>
          </Grid>
        </Paper>
      )}
      
      {/* Available Feeds */}
      {availableFeeds && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Available Data Feeds
          </Typography>
          <Grid container spacing={2}>
            {Object.entries(availableFeeds).map(([feedType, feedInfo]) => (
              <Grid item xs={12} md={6} key={feedType}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography variant="subtitle2" color="primary">
                      {feedType.toUpperCase()}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {feedInfo.description}
                    </Typography>
                    <Typography variant="caption" display="block">
                      Symbols: {feedInfo.symbols}
                    </Typography>
                    <Typography variant="caption" display="block">
                      Frequency: {Array.isArray(feedInfo.frequency) ? feedInfo.frequency.join(', ') : feedInfo.frequency}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Paper>
      )}
      
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
                    
                    <Typography variant="h5" component="div">
                      ${stock.price ? stock.price.toFixed(2) : 'N/A'}
                    </Typography>
                    
                    {stock.bid && stock.ask && (
                      <Stack direction="row" justifyContent="space-between">
                        <Typography variant="body2" color="text.secondary">
                          Bid: ${stock.bid.toFixed(2)}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Ask: ${stock.ask.toFixed(2)}
                        </Typography>
                      </Stack>
                    )}
                    
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Typography 
                        variant="body2" 
                        sx={{ color: getChangeColor(stock.change) }}
                      >
                        {stock.change > 0 ? '+' : ''}{stock.change.toFixed(2)} 
                        ({stock.changePercent > 0 ? '+' : ''}{stock.changePercent.toFixed(2)}%)
                      </Typography>
                    </Stack>
                    
                    {stock.volume && (
                      <Typography variant="caption" color="text.secondary">
                        Volume: {stock.volume.toLocaleString()}
                      </Typography>
                    )}
                    
                    {stock.timestamp && (
                      <Typography variant="caption" color="text.secondary">
                        Updated: {new Date(stock.timestamp).toLocaleTimeString()}
                      </Typography>
                    )}
                    
                    <LinearProgress 
                      variant="determinate" 
                      value={Math.abs(stock.changePercent) * 10} 
                      color={stock.change >= 0 ? 'success' : 'error'}
                      sx={{ height: 8, borderRadius: 4 }}
                    />
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      ) : (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Analytics sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h6" color="text.secondary" gutterBottom>
            WebSocket Disconnected
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Connect to the WebSocket infrastructure to receive real-time market data
          </Typography>
          <Alert severity="info" sx={{ mt: 2, maxWidth: 600, mx: 'auto' }}>
            This page connects to the dedicated WebSocket infrastructure deployed separately from the main application.
            The WebSocket provides real-time quotes, trades, bars, news, and crypto data via Alpaca integration.
          </Alert>
        </Paper>
      )}
    </Box>
  );
};

export default LiveData;