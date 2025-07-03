import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Switch,
  FormControlLabel,
  Alert,
  LinearProgress,
  Badge,
  Divider,
  Button,
  TextField,
  MenuItem,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Pause,
  Refresh,
  Notifications,
  Speed,
  Timeline,
  ShowChart,
  BarChart,
  Visibility,
  VisibilityOff,
  Settings,
  FilterList,
  Add,
  Remove,
  Warning,
  CheckCircle,
  Info
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart as RechartsBarChart,
  Bar,
  Cell,
  PieChart,
  Pie
} from 'recharts';
import { formatCurrency, formatPercentage, formatNumber } from '../utils/formatters';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`dashboard-tabpanel-${index}`}
      aria-labelledby={`dashboard-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const RealTimeDashboard = () => {
  const [tabValue, setTabValue] = useState(0);
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  const [watchlist, setWatchlist] = useState(['AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL']);
  const [marketData, setMarketData] = useState(mockMarketData);
  const [notifications, setNotifications] = useState([]);
  const [refreshInterval, setRefreshInterval] = useState(5); // seconds
  const intervalRef = useRef(null);

  useEffect(() => {
    if (isStreaming) {
      intervalRef.current = setInterval(() => {
        updateMarketData();
        setLastUpdate(new Date());
      }, refreshInterval * 1000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [isStreaming, refreshInterval]);

  const updateMarketData = () => {
    // Simulate real-time data updates
    setMarketData(prevData => ({
      ...prevData,
      watchlistData: prevData.watchlistData.map(stock => ({
        ...stock,
        price: stock.price * (1 + (Math.random() - 0.5) * 0.002), // ±0.1% random movement
        change: stock.price * (Math.random() - 0.5) * 0.002,
        volume: Math.floor(stock.volume * (1 + (Math.random() - 0.5) * 0.1))
      })),
      marketMovers: prevData.marketMovers.map(stock => ({
        ...stock,
        change: stock.change * (1 + (Math.random() - 0.5) * 0.1)
      }))
    }));
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const toggleStreaming = () => {
    setIsStreaming(!isStreaming);
  };

  const addToWatchlist = (symbol) => {
    if (!watchlist.includes(symbol)) {
      setWatchlist([...watchlist, symbol]);
    }
  };

  const removeFromWatchlist = (symbol) => {
    setWatchlist(watchlist.filter(s => s !== symbol));
  };

  const formatTimeAgo = (date) => {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Institutional Real-Time Dashboard
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Professional-grade streaming market data with sub-second latency
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip label="Level II Data" color="primary" size="small" variant="outlined" />
            <Chip label="Market Microstructure" color="success" size="small" variant="outlined" />
            <Chip label="Real-time Analytics" color="info" size="small" variant="outlined" />
            <Chip label={`${refreshInterval}s refresh`} color="warning" size="small" variant="outlined" />
          </Box>
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <Box display="flex" alignItems="center" gap={1} px={2} py={1} bgcolor={isStreaming ? 'success.light' : 'grey.100'} borderRadius={2}>
            <Box 
              width={8} 
              height={8} 
              borderRadius="50%" 
              bgcolor={isStreaming ? 'success.main' : 'grey.500'}
              sx={{ animation: isStreaming ? 'pulse 1s infinite' : 'none' }}
            />
            <Typography variant="body2" fontWeight="bold">
              {isStreaming ? 'LIVE' : 'PAUSED'}
            </Typography>
          </Box>
          
          <Typography variant="body2" color="text.secondary">
            Last update: {formatTimeAgo(lastUpdate)}
          </Typography>
          
          <Button
            variant={isStreaming ? "contained" : "outlined"}
            startIcon={isStreaming ? <Pause /> : <PlayArrow />}
            onClick={toggleStreaming}
            color={isStreaming ? "error" : "success"}
          >
            {isStreaming ? 'Pause' : 'Start'} Stream
          </Button>
          
          <IconButton onClick={updateMarketData} disabled={isStreaming}>
            <Refresh />
          </IconButton>
        </Box>
      </Box>

      {/* Market Status Bar */}
      <Card sx={{ mb: 3, bgcolor: 'primary.dark', color: 'primary.contrastText' }}>
        <CardContent sx={{ py: 2 }}>
          <Box display="flex" alignItems="center" justifyContent="between">
            <Box display="flex" alignItems="center" gap={4}>
              <Box>
                <Typography variant="h6" fontWeight="bold">
                  Market Status: OPEN
                </Typography>
                <Typography variant="body2" opacity={0.8}>
                  NYSE | NASDAQ | Pre-Market 9:30 AM EST
                </Typography>
              </Box>
              
              <Box display="flex" gap={3}>
                <Box textAlign="center">
                  <Typography variant="body2" opacity={0.8}>Trading Volume</Typography>
                  <Typography variant="h6" fontWeight="bold">
                    {formatNumber(marketData.volume.total / 1e9, 1)}B
                  </Typography>
                </Box>
                <Box textAlign="center">
                  <Typography variant="body2" opacity={0.8}>Market Breadth</Typography>
                  <Typography variant="h6" fontWeight="bold">
                    2,845 ↑ / 1,203 ↓
                  </Typography>
                </Box>
                <Box textAlign="center">
                  <Typography variant="body2" opacity={0.8}>VWAP Deviation</Typography>
                  <Typography variant="h6" fontWeight="bold">
                    +0.23%
                  </Typography>
                </Box>
              </Box>
            </Box>
            
            <Box display="flex" alignItems="center" gap={2}>
              <Box textAlign="right">
                <Typography variant="body2" opacity={0.8}>Data Feed Status</Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Box width={6} height={6} borderRadius="50%" bgcolor="success.main" />
                  <Typography variant="body2" fontWeight="bold">Connected</Typography>
                </Box>
              </Box>
            </Box>
          </Box>
        </CardContent>
      </Card>

      {/* Market Overview Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="primary">
                    S&P 500
                  </Typography>
                  <Typography variant="h4">
                    {formatNumber(marketData.indices.sp500.value)}
                  </Typography>
                  <Box display="flex" alignItems="center">
                    {marketData.indices.sp500.change >= 0 ? (
                      <TrendingUp color="success" fontSize="small" />
                    ) : (
                      <TrendingDown color="error" fontSize="small" />
                    )}
                    <Typography 
                      variant="body2" 
                      color={marketData.indices.sp500.change >= 0 ? 'success.main' : 'error.main'}
                    >
                      {formatNumber(marketData.indices.sp500.change)} ({formatPercentage(marketData.indices.sp500.changePercent)})
                    </Typography>
                  </Box>
                </Box>
                <ShowChart color="primary" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="secondary">
                    NASDAQ
                  </Typography>
                  <Typography variant="h4">
                    {formatNumber(marketData.indices.nasdaq.value)}
                  </Typography>
                  <Box display="flex" alignItems="center">
                    {marketData.indices.nasdaq.change >= 0 ? (
                      <TrendingUp color="success" fontSize="small" />
                    ) : (
                      <TrendingDown color="error" fontSize="small" />
                    )}
                    <Typography 
                      variant="body2" 
                      color={marketData.indices.nasdaq.change >= 0 ? 'success.main' : 'error.main'}
                    >
                      {formatNumber(marketData.indices.nasdaq.change)} ({formatPercentage(marketData.indices.nasdaq.changePercent)})
                    </Typography>
                  </Box>
                </Box>
                <Timeline color="secondary" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="info.main">
                    VIX
                  </Typography>
                  <Typography variant="h4">
                    {formatNumber(marketData.vix.value)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {marketData.vix.label}
                  </Typography>
                </Box>
                <Speed color="info" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="warning.main">
                    Volume
                  </Typography>
                  <Typography variant="h4">
                    {formatNumber(marketData.volume.total / 1000000, 0)}M
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    vs {formatNumber(marketData.volume.average / 1000000, 0)}M avg
                  </Typography>
                </Box>
                <BarChart color="warning" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Main Content Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="dashboard tabs">
          <Tab label="Watchlist" icon={<Visibility />} />
          <Tab label="Market Movers" icon={<TrendingUp />} />
          <Tab label="Sector Performance" icon={<BarChart />} />
          <Tab label="Options Flow" icon={<Timeline />} />
          <Tab label="News Feed" icon={<Notifications />} />
        </Tabs>
      </Box>

      <TabPanel value={tabValue} index={0}>
        {/* Advanced Watchlist */}
        <Grid container spacing={3}>
          <Grid item xs={12} lg={8}>
            <Card>
              <CardHeader
                title="Institutional Watchlist"
                subheader="Real-time Level II data with market microstructure analysis"
                action={
                  <Box display="flex" gap={1}>
                    <TextField
                      select
                      size="small"
                      label="Refresh Rate"
                      value={refreshInterval}
                      onChange={(e) => setRefreshInterval(e.target.value)}
                      sx={{ minWidth: 120 }}
                    >
                      <MenuItem value={1}>1 second</MenuItem>
                      <MenuItem value={5}>5 seconds</MenuItem>
                      <MenuItem value={10}>10 seconds</MenuItem>
                      <MenuItem value={30}>30 seconds</MenuItem>
                    </TextField>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={isStreaming}
                          onChange={toggleStreaming}
                          color="primary"
                        />
                      }
                      label="Live Updates"
                    />
                  </Box>
                }
              />
              <CardContent>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Last</TableCell>
                        <TableCell align="right">Bid/Ask</TableCell>
                        <TableCell align="right">Change</TableCell>
                        <TableCell align="right">Volume</TableCell>
                        <TableCell align="right">VWAP</TableCell>
                        <TableCell align="right">Momentum</TableCell>
                        <TableCell align="right">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {marketData.watchlistData.map((stock) => {
                        const vwap = stock.price * (1 + (Math.random() - 0.5) * 0.01);
                        const vwapDiff = ((stock.price - vwap) / vwap) * 100;
                        const momentum = Math.random() * 200 - 100; // -100 to 100
                        
                        return (
                          <TableRow 
                            key={stock.symbol}
                            sx={{ 
                              backgroundColor: stock.alert ? 'warning.light' : 'inherit',
                              '&:hover': { backgroundColor: 'action.hover' }
                            }}
                          >
                            <TableCell>
                              <Box display="flex" alignItems="center">
                                <Typography variant="subtitle2" fontWeight="bold">
                                  {stock.symbol}
                                </Typography>
                                {stock.alert && (
                                  <Chip 
                                    label="Alert" 
                                    color="warning" 
                                    size="small" 
                                    sx={{ ml: 1, height: 16 }}
                                  />
                                )}
                              </Box>
                            </TableCell>
                            
                            <TableCell align="right">
                              <Box textAlign="right">
                                <Typography variant="body2" fontWeight="bold">
                                  {formatCurrency(stock.price)}
                                </Typography>
                                <Typography 
                                  variant="caption" 
                                  color={stock.change >= 0 ? 'success.main' : 'error.main'}
                                >
                                  {stock.change >= 0 ? '+' : ''}{formatCurrency(stock.change)}
                                </Typography>
                              </Box>
                            </TableCell>
                            
                            <TableCell align="right">
                              <Box textAlign="right">
                                <Typography variant="caption" color="text.secondary">
                                  {formatCurrency(stock.price * 0.999)} / {formatCurrency(stock.price * 1.001)}
                                </Typography>
                                <Typography variant="caption" display="block" color="text.secondary">
                                  Spread: {formatCurrency(stock.price * 0.002)}
                                </Typography>
                              </Box>
                            </TableCell>
                            
                            <TableCell align="right">
                              <Chip
                                label={`${stock.changePercent >= 0 ? '+' : ''}${formatPercentage(stock.changePercent)}`}
                                color={stock.changePercent >= 0 ? 'success' : 'error'}
                                size="small"
                                variant="filled"
                              />
                            </TableCell>
                            
                            <TableCell align="right">
                              <Box textAlign="right">
                                <Typography variant="body2">
                                  {formatNumber(stock.volume / 1000)}K
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  vs {formatNumber(stock.volume * 0.8 / 1000)}K avg
                                </Typography>
                              </Box>
                            </TableCell>
                            
                            <TableCell align="right">
                              <Box textAlign="right">
                                <Typography variant="body2">
                                  {formatCurrency(vwap)}
                                </Typography>
                                <Typography 
                                  variant="caption" 
                                  color={vwapDiff >= 0 ? 'success.main' : 'error.main'}
                                >
                                  {vwapDiff >= 0 ? '+' : ''}{vwapDiff.toFixed(2)}%
                                </Typography>
                              </Box>
                            </TableCell>
                            
                            <TableCell align="right">
                              <Box display="flex" alignItems="center" justifyContent="flex-end" gap={1}>
                                <Box width={40} height={20}>
                                  <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={stock.chartData}>
                                      <Line 
                                        type="monotone" 
                                        dataKey="value" 
                                        stroke={stock.changePercent >= 0 ? '#4caf50' : '#f44336'}
                                        strokeWidth={1.5}
                                        dot={false}
                                      />
                                    </LineChart>
                                  </ResponsiveContainer>
                                </Box>
                                <Chip
                                  label={momentum >= 0 ? '↗' : '↘'}
                                  color={momentum >= 0 ? 'success' : 'error'}
                                  size="small"
                                  variant="outlined"
                                />
                              </Box>
                            </TableCell>
                            
                            <TableCell align="right">
                              <Box display="flex" gap={0.5}>
                                <IconButton 
                                  size="small" 
                                  onClick={() => removeFromWatchlist(stock.symbol)}
                                  color="error"
                                >
                                  <Remove />
                                </IconButton>
                                <IconButton 
                                  size="small"
                                  color="primary"
                                >
                                  <Visibility />
                                </IconButton>
                              </Box>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          {/* Market Microstructure Panel */}
          <Grid item xs={12} lg={4}>
            <Grid container spacing={2}>
              {/* Order Flow */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Order Flow Analysis" />
                  <CardContent>
                    <Box mb={2}>
                      <Typography variant="body2" color="text.secondary" mb={1}>
                        Institutional Activity (Last 30min)
                      </Typography>
                      <Box display="flex" justifyContent="between" mb={1}>
                        <Typography variant="body2">Large Orders</Typography>
                        <Chip label="247 blocks" color="primary" size="small" />
                      </Box>
                      <Box display="flex" justifyContent="between" mb={1}>
                        <Typography variant="body2">Dark Pool</Typography>
                        <Chip label="32%" color="secondary" size="small" />
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Sweep Activity</Typography>
                        <Chip label="High" color="warning" size="small" />
                      </Box>
                    </Box>
                    
                    <Box>
                      <Typography variant="body2" color="text.secondary" mb={1}>
                        Buy/Sell Pressure
                      </Typography>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Box flex={0.65} height={8} bgcolor="success.main" borderRadius={1} />
                        <Box flex={0.35} height={8} bgcolor="error.main" borderRadius={1} />
                      </Box>
                      <Box display="flex" justifyContent="between" mt={0.5}>
                        <Typography variant="caption" color="success.main">65% Buy</Typography>
                        <Typography variant="caption" color="error.main">35% Sell</Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Volume Profile */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Volume Profile" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={150}>
                      <BarChart 
                        data={[
                          { price: '185', volume: 40 },
                          { price: '186', volume: 70 },
                          { price: '187', volume: 100 },
                          { price: '188', volume: 85 },
                          { price: '189', volume: 120 },
                          { price: '190', volume: 95 },
                          { price: '191', volume: 60 }
                        ]}
                        layout="horizontal"
                      >
                        <XAxis type="number" hide />
                        <YAxis type="category" dataKey="price" width={40} />
                        <Bar dataKey="volume" fill="#1976d2" />
                      </BarChart>
                    </ResponsiveContainer>
                    <Typography variant="caption" color="text.secondary">
                      Price levels with highest volume concentration
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              {/* Market Alerts */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Real-time Alerts" />
                  <CardContent>
                    <List dense>
                      <ListItem>
                        <ListItemAvatar>
                          <Avatar sx={{ bgcolor: 'warning.main', width: 24, height: 24 }}>
                            <Warning fontSize="small" />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary="AAPL Volume Spike"
                          secondary="3x avg volume in last 5min"
                          primaryTypographyProps={{ variant: 'body2' }}
                          secondaryTypographyProps={{ variant: 'caption' }}
                        />
                      </ListItem>
                      <ListItem>
                        <ListItemAvatar>
                          <Avatar sx={{ bgcolor: 'info.main', width: 24, height: 24 }}>
                            <Info fontSize="small" />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary="TSLA Breakout"
                          secondary="Above 20-day resistance"
                          primaryTypographyProps={{ variant: 'body2' }}
                          secondaryTypographyProps={{ variant: 'caption' }}
                        />
                      </ListItem>
                      <ListItem>
                        <ListItemAvatar>
                          <Avatar sx={{ bgcolor: 'success.main', width: 24, height: 24 }}>
                            <CheckCircle fontSize="small" />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary="NVDA Support Hold"
                          secondary="Bounced off 50-day MA"
                          primaryTypographyProps={{ variant: 'body2' }}
                          secondaryTypographyProps={{ variant: 'caption' }}
                        />
                      </ListItem>
                    </List>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        {/* Market Movers */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Top Gainers" />
              <CardContent>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Price</TableCell>
                        <TableCell align="right">Change</TableCell>
                        <TableCell align="right">Volume</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {marketData.marketMovers.filter(stock => stock.change > 0)
                        .sort((a, b) => b.changePercent - a.changePercent)
                        .slice(0, 10)
                        .map((stock) => (
                        <TableRow key={stock.symbol}>
                          <TableCell>
                            <Typography variant="body2" fontWeight="bold">
                              {stock.symbol}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            {formatCurrency(stock.price)}
                          </TableCell>
                          <TableCell align="right">
                            <Chip
                              label={`+${formatPercentage(stock.changePercent)}`}
                              color="success"
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">
                            {formatNumber(stock.volume / 1000000, 1)}M
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Top Losers" />
              <CardContent>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Price</TableCell>
                        <TableCell align="right">Change</TableCell>
                        <TableCell align="right">Volume</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {marketData.marketMovers.filter(stock => stock.change < 0)
                        .sort((a, b) => a.changePercent - b.changePercent)
                        .slice(0, 10)
                        .map((stock) => (
                        <TableRow key={stock.symbol}>
                          <TableCell>
                            <Typography variant="body2" fontWeight="bold">
                              {stock.symbol}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            {formatCurrency(stock.price)}
                          </TableCell>
                          <TableCell align="right">
                            <Chip
                              label={formatPercentage(stock.changePercent)}
                              color="error"
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">
                            {formatNumber(stock.volume / 1000000, 1)}M
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        {/* Sector Performance */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Sector Performance" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <RechartsBarChart data={marketData.sectorPerformance}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="sector" angle={-45} textAnchor="end" height={80} />
                    <YAxis />
                    <Tooltip formatter={(value) => [`${formatPercentage(value)}`, 'Change']} />
                    <Bar dataKey="change">
                      {marketData.sectorPerformance.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.change >= 0 ? '#4caf50' : '#f44336'} />
                      ))}
                    </Bar>
                  </RechartsBarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Sector Leaders" />
              <CardContent>
                {marketData.sectorPerformance
                  .sort((a, b) => b.change - a.change)
                  .map((sector, index) => (
                  <Box key={sector.sector} display="flex" alignItems="center" justifyContent="between" py={1}>
                    <Typography variant="body2">
                      {sector.sector}
                    </Typography>
                    <Chip
                      label={`${sector.change >= 0 ? '+' : ''}${formatPercentage(sector.change)}`}
                      color={sector.change >= 0 ? 'success' : 'error'}
                      size="small"
                      variant={index === 0 ? 'filled' : 'outlined'}
                    />
                  </Box>
                ))}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={3}>
        {/* Options Flow */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Unusual Options Activity" />
              <CardContent>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Real-time options flow analysis coming soon...
                </Typography>
                <Alert severity="info">
                  This feature will show unusual options activity, large block trades, and smart money flows.
                </Alert>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={4}>
        {/* News Feed */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Live Market News" />
              <CardContent>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Real-time news feed coming soon...
                </Typography>
                <Alert severity="info">
                  This feature will show real-time market news, earnings announcements, and market-moving events.
                </Alert>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>
    </Container>
  );
};

// Mock data for development
const mockMarketData = {
  indices: {
    sp500: { value: 4567.23, change: 12.45, changePercent: 0.27 },
    nasdaq: { value: 14234.56, change: -23.12, changePercent: -0.16 },
  },
  vix: { value: 18.45, label: 'Low Volatility' },
  volume: { total: 3500000000, average: 3200000000 },
  watchlistData: [
    {
      symbol: 'AAPL',
      price: 189.45,
      change: 2.34,
      changePercent: 1.25,
      volume: 45670000,
      alert: false,
      chartData: Array.from({ length: 20 }, (_, i) => ({ value: 185 + Math.random() * 8 }))
    },
    {
      symbol: 'TSLA',
      price: 234.67,
      change: -5.23,
      changePercent: -2.18,
      volume: 67890000,
      alert: true,
      chartData: Array.from({ length: 20 }, (_, i) => ({ value: 230 + Math.random() * 10 }))
    },
    {
      symbol: 'NVDA',
      price: 456.78,
      change: 12.45,
      changePercent: 2.80,
      volume: 34560000,
      alert: false,
      chartData: Array.from({ length: 20 }, (_, i) => ({ value: 450 + Math.random() * 15 }))
    },
    {
      symbol: 'MSFT',
      price: 334.56,
      change: 1.89,
      changePercent: 0.57,
      volume: 23450000,
      alert: false,
      chartData: Array.from({ length: 20 }, (_, i) => ({ value: 330 + Math.random() * 8 }))
    },
    {
      symbol: 'GOOGL',
      price: 134.23,
      change: -2.11,
      changePercent: -1.55,
      volume: 12340000,
      alert: false,
      chartData: Array.from({ length: 20 }, (_, i) => ({ value: 132 + Math.random() * 5 }))
    }
  ],
  marketMovers: [
    { symbol: 'NVDA', price: 456.78, change: 12.45, changePercent: 2.80, volume: 34560000 },
    { symbol: 'AMD', price: 123.45, change: 8.90, changePercent: 7.77, volume: 45670000 },
    { symbol: 'AAPL', price: 189.45, change: 2.34, changePercent: 1.25, volume: 45670000 },
    { symbol: 'TSLA', price: 234.67, change: -5.23, changePercent: -2.18, volume: 67890000 },
    { symbol: 'META', price: 345.67, change: -8.90, changePercent: -2.51, volume: 23450000 },
    { symbol: 'NFLX', price: 456.78, change: -12.34, changePercent: -2.63, volume: 12340000 }
  ],
  sectorPerformance: [
    { sector: 'Technology', change: 1.45 },
    { sector: 'Healthcare', change: 0.78 },
    { sector: 'Financials', change: -0.23 },
    { sector: 'Energy', change: 2.34 },
    { sector: 'Consumer Disc.', change: -1.12 },
    { sector: 'Industrials', change: 0.45 },
    { sector: 'Materials', change: -0.67 },
    { sector: 'Utilities', change: 0.12 },
    { sector: 'Real Estate', change: -0.89 },
    { sector: 'Telecom', change: 0.34 }
  ]
};

export default RealTimeDashboard;