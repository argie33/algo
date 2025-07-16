import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Button,
  CircularProgress,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Tabs,
  Tab,
  LinearProgress,
  Tooltip,
  IconButton,
  Autocomplete,
  Avatar
} from '@mui/material';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter
} from 'recharts';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  Security,
  Warning,
  CheckCircle,
  Info,
  Refresh as RefreshIcon,
  Speed,
  Timeline,
  ShowChart,
  MonetizationOn,
  FlashOn,
  Whatshot,
  Public
} from '@mui/icons-material';

// Generate realistic options flow data
const generateOptionsFlow = () => {
  const flowData = [];
  const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ', 'IWM'];
  
  for (let i = 0; i < 50; i++) {
    const symbol = symbols[Math.floor(Math.random() * symbols.length)];
    const isCall = Math.random() > 0.5;
    const isUnusual = Math.random() > 0.85; // 15% chance of unusual activity
    const volume = Math.floor(Math.random() * 10000) + 100;
    const openInterest = Math.floor(Math.random() * 20000) + 500;
    const volumeOIRatio = volume / openInterest;
    
    const basePrice = 150;
    const strike = Math.round((basePrice + (Math.random() - 0.5) * 50) / 5) * 5;
    const premium = (0.5 + Math.random() * 10).toFixed(2);
    const size = volume * parseFloat(premium) * 100; // Notional size
    
    const time = new Date();
    time.setMinutes(time.getMinutes() - Math.floor(Math.random() * 480)); // Within last 8 hours
    
    flowData.push({
      id: i,
      symbol,
      type: isCall ? 'CALL' : 'PUT',
      strike,
      expiry: '2024-02-16',
      premium,
      volume: volume.toLocaleString(),
      openInterest: openInterest.toLocaleString(),
      volumeOIRatio: volumeOIRatio.toFixed(2),
      notionalSize: size,
      sentiment: volume > 1000 ? (isCall ? 'BULLISH' : 'BEARISH') : 'NEUTRAL',
      time: time.toLocaleTimeString(),
      isUnusual,
      flow: Math.random() > 0.5 ? 'BUY' : 'SELL',
      iv: (0.15 + Math.random() * 0.4).toFixed(3),
      delta: (Math.random() * 0.8).toFixed(3)
    });
  }
  
  return flowData.sort((a, b) => b.notionalSize - a.notionalSize);
};

// Calculate flow metrics
const calculateFlowMetrics = (flowData) => {
  const callFlow = flowData.filter(f => f.type === 'CALL');
  const putFlow = flowData.filter(f => f.type === 'PUT');
  
  const callVolume = callFlow.reduce((sum, f) => sum + parseInt(f.volume.replace(/,/g, '')), 0);
  const putVolume = putFlow.reduce((sum, f) => sum + parseInt(f.volume.replace(/,/g, '')), 0);
  
  const totalNotional = flowData.reduce((sum, f) => sum + f.notionalSize, 0);
  const unusualCount = flowData.filter(f => f.isUnusual).length;
  
  const topSymbols = {};
  flowData.forEach(f => {
    topSymbols[f.symbol] = (topSymbols[f.symbol] || 0) + f.notionalSize;
  });
  
  return {
    putCallRatio: (putVolume / callVolume).toFixed(2),
    totalVolume: (callVolume + putVolume).toLocaleString(),
    totalNotional: (totalNotional / 1000000).toFixed(1),
    unusualActivity: unusualCount,
    topSymbols: Object.entries(topSymbols)
      .sort(([,a], [,b]) => b - a)
      .slice(0, 5)
      .map(([symbol, notional]) => ({ symbol, notional: (notional / 1000000).toFixed(1) }))
  };
};

// Generate sector flow data
const generateSectorFlow = () => {
  const sectors = [
    { name: 'Technology', flow: 145.2, sentiment: 'BULLISH' },
    { name: 'Healthcare', flow: 89.7, sentiment: 'NEUTRAL' },
    { name: 'Financial', flow: 123.4, sentiment: 'BEARISH' },
    { name: 'Energy', flow: 67.3, sentiment: 'BULLISH' },
    { name: 'Consumer', flow: 98.1, sentiment: 'NEUTRAL' },
    { name: 'Industrial', flow: 76.8, sentiment: 'BEARISH' },
    { name: 'Materials', flow: 45.2, sentiment: 'NEUTRAL' },
    { name: 'Utilities', flow: 23.1, sentiment: 'BULLISH' }
  ];
  
  return sectors;
};

const OptionsFlow = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [flowData, setFlowData] = useState([]);
  const [flowMetrics, setFlowMetrics] = useState(null);
  const [sectorFlow, setSectorFlow] = useState([]);
  const [timeFilter, setTimeFilter] = useState('1H');
  const [sizeFilter, setSizeFilter] = useState(1000000); // $1M minimum
  const [symbolFilter, setSymbolFilter] = useState('ALL');
  
  const symbols = ['ALL', 'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ'];
  const timeFilters = ['15M', '1H', '4H', '1D'];
  
  useEffect(() => {
    loadFlowData();
    const interval = setInterval(loadFlowData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [timeFilter, sizeFilter, symbolFilter]);
  
  const loadFlowData = () => {
    setLoading(true);
    
    try {
      let data = generateOptionsFlow();
      
      // Apply filters
      if (symbolFilter !== 'ALL') {
        data = data.filter(f => f.symbol === symbolFilter);
      }
      
      data = data.filter(f => f.notionalSize >= sizeFilter);
      
      const metrics = calculateFlowMetrics(data);
      const sectors = generateSectorFlow();
      
      setFlowData(data);
      setFlowMetrics(metrics);
      setSectorFlow(sectors);
      
    } catch (err) {
      setError('Failed to load options flow data');
    } finally {
      setLoading(false);
    }
  };
  
  const getSentimentColor = (sentiment) => {
    switch (sentiment) {
      case 'BULLISH': return 'success.main';
      case 'BEARISH': return 'error.main';
      default: return 'text.secondary';
    }
  };
  
  const getFlowColor = (flow) => {
    return flow === 'BUY' ? 'success.main' : 'error.main';
  };
  
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8'];
  
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={700} gutterBottom>
          Options Flow Analysis
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Real-time options order flow, unusual activity detection, and market sentiment analysis
        </Typography>
        <Box display="flex" gap={1} flexWrap="wrap">
          <Chip label="Live Flow" color="primary" size="small" variant="outlined" />
          <Chip label="Unusual Activity" color="success" size="small" variant="outlined" />
          <Chip label="Sentiment Analysis" color="info" size="small" variant="outlined" />
          <Chip label="Volume Analysis" color="warning" size="small" variant="outlined" />
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Controls */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Time Frame</InputLabel>
                <Select
                  value={timeFilter}
                  label="Time Frame"
                  onChange={(e) => setTimeFilter(e.target.value)}
                >
                  {timeFilters.map(time => (
                    <MenuItem key={time} value={time}>{time}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Symbol</InputLabel>
                <Select
                  value={symbolFilter}
                  label="Symbol"
                  onChange={(e) => setSymbolFilter(e.target.value)}
                >
                  {symbols.map(symbol => (
                    <MenuItem key={symbol} value={symbol}>{symbol}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={2}>
              <TextField
                label="Min Size ($M)"
                type="number"
                value={sizeFilter / 1000000}
                onChange={(e) => setSizeFilter(parseFloat(e.target.value) * 1000000)}
                size="small"
                fullWidth
              />
            </Grid>
            <Grid item xs={12} sm={2}>
              <Button
                variant="contained"
                startIcon={loading ? <CircularProgress size={16} /> : <RefreshIcon />}
                onClick={loadFlowData}
                disabled={loading}
                fullWidth
              >
                Refresh
              </Button>
            </Grid>
            <Grid item xs={12} sm={4}>
              {flowMetrics && (
                <Box display="flex" gap={2}>
                  <Box textAlign="center">
                    <Typography variant="caption" color="text.secondary">P/C Ratio</Typography>
                    <Typography variant="h6" fontWeight="bold">
                      {flowMetrics.putCallRatio}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="caption" color="text.secondary">Total Volume</Typography>
                    <Typography variant="h6" fontWeight="bold">
                      {flowMetrics.totalVolume}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="caption" color="text.secondary">Unusual</Typography>
                    <Typography variant="h6" fontWeight="bold" color="warning.main">
                      {flowMetrics.unusualActivity}
                    </Typography>
                  </Box>
                </Box>
              )}
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        {/* Main Flow Table */}
        <Grid item xs={12} lg={8}>
          <Card>
            <CardHeader 
              title="Options Flow"
              subheader={`${flowData.length} transactions in last ${timeFilter}`}
              action={
                <Chip 
                  label="LIVE" 
                  color="success" 
                  size="small" 
                  icon={<FlashOn />}
                />
              }
            />
            <CardContent>
              <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 2 }}>
                <Tab label="Flow Feed" />
                <Tab label="Unusual Activity" />
                <Tab label="Volume Leaders" />
                <Tab label="Sector Flow" />
              </Tabs>
              
              {activeTab === 0 && (
                <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 600 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Time</TableCell>
                        <TableCell>Symbol</TableCell>
                        <TableCell>Type</TableCell>
                        <TableCell>Strike</TableCell>
                        <TableCell align="right">Premium</TableCell>
                        <TableCell align="right">Volume</TableCell>
                        <TableCell align="right">Size ($M)</TableCell>
                        <TableCell>Flow</TableCell>
                        <TableCell>Sentiment</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {flowData.slice(0, 50).map((flow) => (
                        <TableRow key={flow.id} hover sx={{ bgcolor: flow.isUnusual ? 'warning.light' : 'inherit' }}>
                          <TableCell>
                            <Typography variant="caption">{flow.time}</Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" fontWeight="bold">
                              {flow.symbol}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label={flow.type} 
                              color={flow.type === 'CALL' ? 'success' : 'error'}
                              size="small"
                              variant="outlined"
                            />
                          </TableCell>
                          <TableCell>${flow.strike}</TableCell>
                          <TableCell align="right">${flow.premium}</TableCell>
                          <TableCell align="right">{flow.volume}</TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontWeight="bold">
                              ${(flow.notionalSize / 1000000).toFixed(1)}M
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label={flow.flow} 
                              color={flow.flow === 'BUY' ? 'success' : 'error'}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>
                            <Typography sx={{ color: getSentimentColor(flow.sentiment) }}>
                              {flow.sentiment}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
              
              {activeTab === 1 && (
                <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 600 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell>Details</TableCell>
                        <TableCell align="right">Volume</TableCell>
                        <TableCell align="right">Vol/OI</TableCell>
                        <TableCell align="right">Size</TableCell>
                        <TableCell>Significance</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {flowData.filter(f => f.isUnusual).map((flow) => (
                        <TableRow key={flow.id} hover>
                          <TableCell>
                            <Box display="flex" alignItems="center" gap={1}>
                              <Whatshot color="warning" fontSize="small" />
                              <Typography variant="body2" fontWeight="bold">
                                {flow.symbol}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">
                              {flow.type} ${flow.strike} {flow.expiry}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">{flow.volume}</TableCell>
                          <TableCell align="right">
                            <Typography 
                              variant="body2" 
                              fontWeight="bold"
                              color={parseFloat(flow.volumeOIRatio) > 2 ? 'error.main' : 'text.primary'}
                            >
                              {flow.volumeOIRatio}x
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            ${(flow.notionalSize / 1000000).toFixed(1)}M
                          </TableCell>
                          <TableCell>
                            <Chip 
                              label="HIGH" 
                              color="warning" 
                              size="small"
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
              
              {activeTab === 2 && flowMetrics && (
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart data={flowMetrics.topSymbols}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" />
                    <YAxis label={{ value: 'Notional ($M)', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip formatter={(value) => [`$${value}M`, 'Notional']} />
                    <Bar dataKey="notional" fill="#8884d8" />
                  </BarChart>
                </ResponsiveContainer>
              )}
              
              {activeTab === 3 && (
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={sectorFlow}
                          cx="50%"
                          cy="50%"
                          outerRadius={100}
                          fill="#8884d8"
                          dataKey="flow"
                          label={({ name, value }) => `${name}: $${value}M`}
                        >
                          {sectorFlow.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <RechartsTooltip formatter={(value) => [`$${value}M`, 'Flow']} />
                      </PieChart>
                    </ResponsiveContainer>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TableContainer component={Paper} variant="outlined">
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Sector</TableCell>
                            <TableCell align="right">Flow ($M)</TableCell>
                            <TableCell>Sentiment</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {sectorFlow.map((sector, index) => (
                            <TableRow key={sector.name}>
                              <TableCell>{sector.name}</TableCell>
                              <TableCell align="right">${sector.flow}M</TableCell>
                              <TableCell>
                                <Typography sx={{ color: getSentimentColor(sector.sentiment) }}>
                                  {sector.sentiment}
                                </Typography>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Grid>
                </Grid>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Sidebar */}
        <Grid item xs={12} lg={4}>
          {/* Market Sentiment */}
          <Card sx={{ mb: 3 }}>
            <CardHeader title="Market Sentiment" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Overall</Typography>
                  <Typography variant="h6" fontWeight="bold" color="success.main">
                    BULLISH
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Strength</Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={72} 
                    color="success"
                    sx={{ mt: 1 }}
                  />
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary">
                    Based on call/put flow analysis and unusual activity patterns
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* Flow Indicators */}
          <Card sx={{ mb: 3 }}>
            <CardHeader title="Flow Indicators" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Call Flow</Typography>
                  <Typography variant="h6" fontWeight="bold" color="success.main">
                    65%
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Put Flow</Typography>
                  <Typography variant="h6" fontWeight="bold" color="error.main">
                    35%
                  </Typography>
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary">Smart Money</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    Net Buying Calls
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* Today's Highlights */}
          <Card>
            <CardHeader title="Today's Highlights" />
            <CardContent>
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  🔥 Most Unusual Activity
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  TSLA Feb 160 Calls - 15,000 contracts (10x normal volume)
                </Typography>
                
                <Typography variant="subtitle2" gutterBottom>
                  📈 Largest Flow
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  SPY Weekly Puts - $45M notional
                </Typography>
                
                <Typography variant="subtitle2" gutterBottom>
                  ⚡ Hot Sectors
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Technology (+$145M), Financial (-$123M)
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
};

export default OptionsFlow;