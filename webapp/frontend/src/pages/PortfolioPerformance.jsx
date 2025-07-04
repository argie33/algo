import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
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
  CircularProgress,
  Alert,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  ComposedChart,
  ScatterChart,
  Scatter,
  PieChart,
  Pie,
  Cell
} from 'recharts';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  Timeline,
  PieChart as PieChartIcon,
  ShowChart,
  AccountBalance,
  Warning,
  CheckCircle,
  Info,
  Star,
  StarBorder
} from '@mui/icons-material';
import { getPortfolioPerformance, getPortfolioAnalytics, getBenchmarkData } from '../services/api';

const PortfolioPerformance = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeframe, setTimeframe] = useState('1Y');
  const [showBenchmark, setShowBenchmark] = useState(true);
  const [performanceData, setPerformanceData] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [attributionData, setAttributionData] = useState(null);
  const [riskMetrics, setRiskMetrics] = useState(null);

  // Performance metrics
  const [metrics, setMetrics] = useState({
    totalReturn: 0,
    annualizedReturn: 0,
    volatility: 0,
    sharpeRatio: 0,
    maxDrawdown: 0,
    beta: 0,
    alpha: 0,
    informationRatio: 0,
    calmarRatio: 0,
    sortinoRatio: 0
  });

  const isPremium = true; // Removed premium restriction - available to all users

  useEffect(() => {
    fetchPerformanceData();
  }, [timeframe]);

  const fetchPerformanceData = async () => {
    try {
      setLoading(true);
      
      // Fetch portfolio performance data
      const performanceResponse = await getPortfolioPerformance(timeframe);
      const perfData = performanceResponse?.data || performanceResponse;
      
      if (perfData) {
        // Transform performance data
        const transformedData = perfData.performance || perfData.data || [];
        setPerformanceData(transformedData);
        
        // Extract or use default metrics
        const responseMetrics = perfData.metrics || {};
        setMetrics({
          totalReturn: responseMetrics.totalReturn || responseMetrics.totalReturnPercent || 0,
          annualizedReturn: responseMetrics.annualizedReturn || 0,
          volatility: responseMetrics.volatility || 0,
          sharpeRatio: responseMetrics.sharpeRatio || 0,
          maxDrawdown: responseMetrics.maxDrawdown || 0,
          beta: responseMetrics.beta || 1,
          alpha: responseMetrics.alpha || 0,
          informationRatio: responseMetrics.informationRatio || 0,
          calmarRatio: responseMetrics.calmarRatio || 0,
          sortinoRatio: responseMetrics.sortinoRatio || 0
        });
      }

      // Fetch analytics (premium feature)
      if (isPremium) {
        try {
          const analyticsResponse = await getPortfolioAnalytics(timeframe);
          const analyticsData = analyticsResponse?.data || analyticsResponse;
          
          if (analyticsData) {
            setAnalytics(analyticsData.analytics || analyticsData);
            setAttributionData(analyticsData.attribution);
            setRiskMetrics(analyticsData.risk);
          }
        } catch (analyticsError) {
          console.log('Analytics fetch failed, using mock data');
          // Generate mock analytics data
          setAnalytics({
            sectorPerformance: [
              { sector: 'Technology', return: 15.2 },
              { sector: 'Healthcare', return: 8.7 },
              { sector: 'Financials', return: 12.1 }
            ],
            holdingsPerformance: [
              { symbol: 'AAPL', name: 'Apple Inc.', weight: 28.5, return: 13.1, contribution: 3.7, volatility: 25.2, rating: 4 },
              { symbol: 'MSFT', name: 'Microsoft Corp.', weight: 22.9, return: 8.9, contribution: 2.0, volatility: 22.1, rating: 5 },
              { symbol: 'GOOGL', name: 'Alphabet Inc.', weight: 18.5, return: 7.6, contribution: 1.4, volatility: 28.4, rating: 4 }
            ]
          });
          
          setAttributionData({
            sectorAttribution: [
              { name: 'Technology', contribution: 5.8 },
              { name: 'Healthcare', contribution: 1.2 },
              { name: 'Financials', contribution: 2.1 }
            ],
            stockAttribution: [
              { symbol: 'AAPL', weight: 28.5, return: 13.1, contribution: 3.7 },
              { symbol: 'MSFT', weight: 22.9, return: 8.9, contribution: 2.0 },
              { symbol: 'GOOGL', weight: 18.5, return: 7.6, contribution: 1.4 }
            ]
          });
          
          setRiskMetrics({
            rollingVolatility: Array.from({ length: 30 }, (_, i) => ({
              date: new Date(Date.now() - (30 - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
              volatility: 18 + Math.random() * 8
            }))
          });
        }
      }
    } catch (err) {
      setError('Failed to fetch performance data');
      console.error('Performance fetch error:', err);
      
      // Set mock data on error
      setPerformanceData([]);
      setMetrics({
        totalReturn: 0,
        annualizedReturn: 0,
        volatility: 0,
        sharpeRatio: 0,
        maxDrawdown: 0,
        beta: 1,
        alpha: 0,
        informationRatio: 0,
        calmarRatio: 0,
        sortinoRatio: 0
      });
    } finally {
      setLoading(false);
    }
  };

  const formatPercentage = (value) => {
    const color = value >= 0 ? 'success.main' : 'error.main';
    const sign = value >= 0 ? '+' : '';
    return {
      text: `${sign}${value.toFixed(2)}%`,
      color
    };
  };

  const formatCurrency = (value) => {
    return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <Paper sx={{ p: 2, border: 1, borderColor: 'divider' }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {label}
          </Typography>
          {payload.map((entry, index) => (
            <Typography
              key={index}
              variant="body2"
              sx={{ color: entry.color }}
            >
              {entry.name}: {entry.name.includes('%') ? `${entry.value.toFixed(2)}%` : formatCurrency(entry.value)}
            </Typography>
          ))}
        </Paper>
      );
    }
    return null;
  };

  const TabPanel = ({ children, value, index, ...other }) => (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`performance-tabpanel-${index}`}
      aria-labelledby={`performance-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );

  if (!isPremium) {
    return (
      <Container maxWidth="xl">
        <Box sx={{ mb: 4 }}>
          <Typography variant="h4" gutterBottom>
            Portfolio Performance Analysis
          </Typography>
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="body1">
              Performance analysis with attribution is a premium feature. 
              Upgrade your account to access detailed portfolio analytics, attribution analysis, and advanced risk metrics.
            </Typography>
            <Button variant="contained" sx={{ mt: 2 }}>
              Upgrade to Premium
            </Button>
          </Alert>
        </Box>
      </Container>
    );
  }

  if (loading) {
    return (
      <Container maxWidth="xl">
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl">
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Portfolio Performance Analysis
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Comprehensive performance analytics with attribution analysis
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Controls */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <FormControl sx={{ minWidth: 120 }}>
          <InputLabel>Timeframe</InputLabel>
          <Select
            value={timeframe}
            label="Timeframe"
            onChange={(e) => setTimeframe(e.target.value)}
          >
            <MenuItem value="1M">1 Month</MenuItem>
            <MenuItem value="3M">3 Months</MenuItem>
            <MenuItem value="6M">6 Months</MenuItem>
            <MenuItem value="1Y">1 Year</MenuItem>
            <MenuItem value="2Y">2 Years</MenuItem>
            <MenuItem value="3Y">3 Years</MenuItem>
            <MenuItem value="5Y">5 Years</MenuItem>
            <MenuItem value="MAX">All Time</MenuItem>
          </Select>
        </FormControl>
        <FormControlLabel
          control={
            <Switch
              checked={showBenchmark}
              onChange={(e) => setShowBenchmark(e.target.checked)}
            />
          }
          label="Show Benchmark"
        />
      </Box>

      {/* Performance Metrics Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                Total Return
              </Typography>
              <Typography variant="h5" sx={{ color: formatPercentage(metrics.totalReturn).color }}>
                {formatPercentage(metrics.totalReturn).text}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Since inception
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                Annualized Return
              </Typography>
              <Typography variant="h5" sx={{ color: formatPercentage(metrics.annualizedReturn).color }}>
                {formatPercentage(metrics.annualizedReturn).text}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Geometric mean
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                Sharpe Ratio
              </Typography>
              <Typography variant="h5">
                {metrics.sharpeRatio.toFixed(2)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Risk-adjusted return
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                Max Drawdown
              </Typography>
              <Typography variant="h5" color="error.main">
                {formatPercentage(metrics.maxDrawdown).text}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Worst decline
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs for different analysis views */}
      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)}>
            <Tab label="Performance Chart" icon={<ShowChart />} />
            <Tab label="Attribution Analysis" icon={<PieChartIcon />} />
            <Tab label="Risk Metrics" icon={<Warning />} />
            <Tab label="Sector Performance" icon={<Analytics />} />
            <Tab label="Holdings Analysis" icon={<Assessment />} />
          </Tabs>
        </Box>

        {/* Performance Chart Tab */}
        <TabPanel value={activeTab} index={0}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Portfolio Performance vs Benchmark
            </Typography>
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={performanceData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <RechartsTooltip content={<CustomTooltip />} />
                <Area
                  type="monotone"
                  dataKey="portfolioValue"
                  stroke="#2196F3"
                  fill="#2196F3"
                  fillOpacity={0.1}
                  name="Portfolio Value"
                />
                {showBenchmark && (
                  <Line
                    type="monotone"
                    dataKey="benchmarkValue"
                    stroke="#FF9800"
                    strokeWidth={2}
                    dot={false}
                    name="S&P 500"
                  />
                )}
                <Bar
                  dataKey="dailyReturn"
                  fill="#4CAF50"
                  name="Daily Return %"
                  yAxisId="right"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </TabPanel>

        {/* Attribution Analysis Tab */}
        <TabPanel value={activeTab} index={1}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Performance Attribution Analysis
            </Typography>
            {attributionData ? (
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle1" gutterBottom>
                    Sector Attribution
                  </Typography>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={attributionData.sectorAttribution}
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="contribution"
                        label={({ name, contribution }) => `${name}: ${contribution.toFixed(2)}%`}
                      >
                        {attributionData.sectorAttribution.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.contribution >= 0 ? '#4CAF50' : '#F44336'} />
                        ))}
                      </Pie>
                      <RechartsTooltip formatter={(value) => [`${value.toFixed(2)}%`, 'Contribution']} />
                    </PieChart>
                  </ResponsiveContainer>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle1" gutterBottom>
                    Stock Attribution
                  </Typography>
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Stock</TableCell>
                          <TableCell align="right">Weight</TableCell>
                          <TableCell align="right">Return</TableCell>
                          <TableCell align="right">Contribution</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {attributionData.stockAttribution?.slice(0, 10).map((stock) => (
                          <TableRow key={stock.symbol}>
                            <TableCell>{stock.symbol}</TableCell>
                            <TableCell align="right">{stock.weight.toFixed(2)}%</TableCell>
                            <TableCell 
                              align="right"
                              sx={{ color: stock.return >= 0 ? 'success.main' : 'error.main' }}
                            >
                              {formatPercentage(stock.return).text}
                            </TableCell>
                            <TableCell 
                              align="right"
                              sx={{ color: stock.contribution >= 0 ? 'success.main' : 'error.main' }}
                            >
                              {formatPercentage(stock.contribution).text}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Grid>
              </Grid>
            ) : (
              <Typography color="text.secondary">No attribution data available</Typography>
            )}
          </CardContent>
        </TabPanel>

        {/* Risk Metrics Tab */}
        <TabPanel value={activeTab} index={2}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Risk Analysis
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle1" gutterBottom>
                  Risk Metrics
                </Typography>
                <List>
                  <ListItem>
                    <ListItemIcon>
                      <Analytics />
                    </ListItemIcon>
                    <ListItemText
                      primary="Volatility (Annualized)"
                      secondary={`${metrics.volatility.toFixed(2)}%`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <TrendingUp />
                    </ListItemIcon>
                    <ListItemText
                      primary="Beta (vs S&P 500)"
                      secondary={metrics.beta.toFixed(2)}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <Star />
                    </ListItemIcon>
                    <ListItemText
                      primary="Alpha (Annualized)"
                      secondary={`${metrics.alpha.toFixed(2)}%`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <Assessment />
                    </ListItemIcon>
                    <ListItemText
                      primary="Information Ratio"
                      secondary={metrics.informationRatio.toFixed(2)}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <CheckCircle />
                    </ListItemIcon>
                    <ListItemText
                      primary="Sortino Ratio"
                      secondary={metrics.sortinoRatio.toFixed(2)}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <Warning />
                    </ListItemIcon>
                    <ListItemText
                      primary="Calmar Ratio"
                      secondary={metrics.calmarRatio.toFixed(2)}
                    />
                  </ListItem>
                </List>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="subtitle1" gutterBottom>
                  Rolling Volatility
                </Typography>
                {riskMetrics?.rollingVolatility && (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={riskMetrics.rollingVolatility}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip content={<CustomTooltip />} />
                      <Line
                        type="monotone"
                        dataKey="volatility"
                        stroke="#FF5722"
                        strokeWidth={2}
                        dot={false}
                        name="30-Day Volatility %"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </Grid>
            </Grid>
          </CardContent>
        </TabPanel>

        {/* Sector Performance Tab */}
        <TabPanel value={activeTab} index={3}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Sector Performance Analysis
            </Typography>
            {analytics?.sectorPerformance && (
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={analytics.sectorPerformance}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="sector" angle={-45} textAnchor="end" height={100} />
                  <YAxis />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Bar dataKey="return" name="Return %" fill="#2196F3" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </TabPanel>

        {/* Holdings Analysis Tab */}
        <TabPanel value={activeTab} index={4}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Top Holdings Performance
            </Typography>
            {analytics?.holdingsPerformance && (
              <TableContainer component={Paper} variant="outlined">
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Name</TableCell>
                      <TableCell align="right">Weight</TableCell>
                      <TableCell align="right">Return</TableCell>
                      <TableCell align="right">Contribution</TableCell>
                      <TableCell align="right">Volatility</TableCell>
                      <TableCell>Rating</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {analytics.holdingsPerformance.map((holding) => (
                      <TableRow key={holding.symbol}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {holding.symbol}
                          </Typography>
                        </TableCell>
                        <TableCell>{holding.name}</TableCell>
                        <TableCell align="right">{holding.weight.toFixed(2)}%</TableCell>
                        <TableCell 
                          align="right"
                          sx={{ color: holding.return >= 0 ? 'success.main' : 'error.main' }}
                        >
                          {formatPercentage(holding.return).text}
                        </TableCell>
                        <TableCell 
                          align="right"
                          sx={{ color: holding.contribution >= 0 ? 'success.main' : 'error.main' }}
                        >
                          {formatPercentage(holding.contribution).text}
                        </TableCell>
                        <TableCell align="right">{holding.volatility.toFixed(2)}%</TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            {[1, 2, 3, 4, 5].map((star) => (
                              star <= holding.rating ? 
                                <Star key={star} sx={{ color: '#FFD700', fontSize: 16 }} /> :
                                <StarBorder key={star} sx={{ color: '#FFD700', fontSize: 16 }} />
                            ))}
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        </TabPanel>
      </Card>
    </Container>
  );
};

export default PortfolioPerformance;