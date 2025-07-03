import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
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
  TextField,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tooltip,
  Badge,
  LinearProgress,
  Divider,
  Slider,
  Switch,
  FormControlLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  TablePagination,
  TableSortLabel,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Autocomplete,
  Rating,
  Stack,
  List,
  ListItem
} from '@mui/material';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  AreaChart,
  ScatterChart,
  Scatter,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Treemap,
  ComposedChart
} from 'recharts';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Add,
  Delete,
  Edit,
  Assessment,
  AccountBalance,
  ShowChart,
  Timeline,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon,
  Warning,
  CheckCircle,
  Info,
  Upload,
  Download,
  Security,
  NotificationsActive,
  Notifications,
  Settings,
  ExpandMore,
  Report,
  Speed,
  BusinessCenter,
  Psychology,
  TrendingFlat,
  School,
  Shield,
  Lightbulb,
  StarRate,
  CompareArrows,
  AccountBalanceWallet
} from '@mui/icons-material';
import { getApiConfig } from '../services/api';
import { formatCurrency, formatPercentage, formatNumber } from '../utils/formatters';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`portfolio-tabpanel-${index}`}
      aria-labelledby={`portfolio-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const Portfolio = () => {
  const { apiUrl: API_BASE } = getApiConfig();
  const { user, isAuthenticated, isLoading, tokens } = useAuth();
  const navigate = useNavigate();
  
  const [activeTab, setActiveTab] = useState(0);
  const [portfolioData, setPortfolioData] = useState(mockPortfolioData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Authentication guard
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/login');
    }
  }, [isAuthenticated, isLoading, navigate]);

  // Load user-specific portfolio data
  useEffect(() => {
    if (isAuthenticated && user) {
      loadUserPortfolio();
    }
  }, [isAuthenticated, user]);

  const loadUserPortfolio = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Try to fetch real portfolio data first
      try {
        const response = await fetch(`${API_BASE}/api/portfolio/analytics?timeframe=${timeframe}`, {
          headers: {
            'Authorization': `Bearer ${tokens?.accessToken || 'dev-token'}`
          }
        });
        
        if (response.ok) {
          const realPortfolioData = await response.json();
          if (realPortfolioData && realPortfolioData.holdings) {
            setPortfolioData({
              ...realPortfolioData,
              userId: user.userId,
              username: user.username,
              lastUpdated: new Date().toISOString(),
              preferences: {
                displayCurrency: 'USD',
                timeZone: 'America/New_York',
                riskTolerance: 'moderate',
                investmentStyle: 'growth'
              }
            });
            return;
          }
        }
      } catch (apiError) {
        console.log('Portfolio API not available, using enhanced mock data');
      }
      
      // Generate enhanced mock data with realistic market simulation
      const enhancedMockData = generateRealisticPortfolioData(user);
      setPortfolioData(enhancedMockData);
      
    } catch (error) {
      console.error('Error loading portfolio:', error);
      setError('Failed to load portfolio data');
    } finally {
      setLoading(false);
    }
  };

  // Generate realistic portfolio data that simulates market conditions
  const generateRealisticPortfolioData = (user) => {
    const now = new Date();
    const marketOpen = now.getHours() >= 9 && now.getHours() < 16; // Simple market hours check
    
    // Simulate market volatility
    const volatilityMultiplier = marketOpen ? 1 + (Math.random() - 0.5) * 0.02 : 1;
    
    const baseHoldings = [
      { symbol: 'AAPL', company: 'Apple Inc.', shares: 100, avgCost: 150.00, sector: 'Technology', beta: 1.2 },
      { symbol: 'MSFT', company: 'Microsoft Corp.', shares: 75, avgCost: 240.00, sector: 'Technology', beta: 0.9 },
      { symbol: 'GOOGL', company: 'Alphabet Inc.', shares: 50, avgCost: 120.00, sector: 'Technology', beta: 1.1 },
      { symbol: 'TSLA', company: 'Tesla Inc.', shares: 25, avgCost: 200.00, sector: 'Consumer Cyclical', beta: 2.0 },
      { symbol: 'NVDA', company: 'NVIDIA Corp.', shares: 40, avgCost: 300.00, sector: 'Technology', beta: 1.7 },
      { symbol: 'AMZN', company: 'Amazon.com Inc.', shares: 30, avgCost: 130.00, sector: 'Consumer Cyclical', beta: 1.3 },
      { symbol: 'META', company: 'Meta Platforms Inc.', shares: 60, avgCost: 180.00, sector: 'Technology', beta: 1.4 },
      { symbol: 'SPY', company: 'SPDR S&P 500 ETF', shares: 200, avgCost: 400.00, sector: 'ETF', beta: 1.0 }
    ];

    // Simulate realistic current prices with daily volatility
    const holdings = baseHoldings.map(holding => {
      const dayOfYear = Math.floor((now - new Date(now.getFullYear(), 0, 0)) / 86400000);
      const volatility = holding.beta * 0.02 * Math.sin(dayOfYear / 365 * 2 * Math.PI) * volatilityMultiplier;
      const trend = Math.sin((dayOfYear + holding.symbol.length * 10) / 50) * 0.1;
      
      const currentPrice = holding.avgCost * (1 + trend + volatility + (Math.random() - 0.5) * 0.05);
      const marketValue = currentPrice * holding.shares;
      const costBasis = holding.avgCost * holding.shares;
      const gainLoss = marketValue - costBasis;
      const gainLossPercent = (gainLoss / costBasis) * 100;
      
      return {
        ...holding,
        currentPrice: Math.round(currentPrice * 100) / 100,
        marketValue: Math.round(marketValue * 100) / 100,
        gainLoss: Math.round(gainLoss * 100) / 100,
        gainLossPercent: Math.round(gainLossPercent * 100) / 100,
        allocation: 0, // Will be calculated below
        volume: Math.floor(Math.random() * 10000000) + 1000000,
        dayChange: Math.round((Math.random() - 0.5) * 10 * 100) / 100,
        dayChangePercent: Math.round((Math.random() - 0.5) * 5 * 100) / 100
      };
    });

    // Calculate allocations
    const totalValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
    holdings.forEach(holding => {
      holding.allocation = Math.round((holding.marketValue / totalValue) * 100 * 100) / 100;
    });

    return {
      userId: user.userId,
      username: user.username,
      lastUpdated: now.toISOString(),
      preferences: {
        displayCurrency: 'USD',
        timeZone: 'America/New_York',
        riskTolerance: 'moderate',
        investmentStyle: 'growth'
      },
      holdings,
      totalValue,
      totalCost: holdings.reduce((sum, h) => sum + (h.avgCost * h.shares), 0),
      performanceHistory: generatePerformanceHistory(),
      sectorAllocation: generateSectorAllocation(holdings),
      riskMetrics: generateRiskMetrics(holdings),
      stressTests: generateStressTests()
    };
  };

  const generatePerformanceHistory = () => {
    const history = [];
    const baseValue = 100000;
    let currentValue = baseValue;
    
    for (let i = 30; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      
      // Simulate market performance with some volatility
      const dailyChange = (Math.random() - 0.48) * 0.02; // Slight upward bias
      currentValue *= (1 + dailyChange);
      
      history.push({
        date: date.toISOString().split('T')[0],
        value: Math.round(currentValue),
        change: Math.round((currentValue - baseValue) * 100) / 100,
        changePercent: Math.round(((currentValue - baseValue) / baseValue) * 100 * 100) / 100
      });
    }
    
    return history;
  };

  const generateSectorAllocation = (holdings) => {
    const sectors = {};
    holdings.forEach(holding => {
      const sector = holding.sector || 'Other';
      if (!sectors[sector]) {
        sectors[sector] = { value: 0, count: 0 };
      }
      sectors[sector].value += holding.marketValue;
      sectors[sector].count += 1;
    });
    
    return Object.entries(sectors).map(([name, data]) => ({
      name,
      value: Math.round(data.value),
      allocation: Math.round((data.value / holdings.reduce((sum, h) => sum + h.marketValue, 0)) * 100 * 100) / 100,
      count: data.count
    }));
  };

  const generateRiskMetrics = (holdings) => {
    return {
      var95: Math.round(holdings.reduce((sum, h) => sum + h.marketValue, 0) * 0.05),
      volatility: Math.round((holdings.reduce((sum, h) => sum + (h.beta || 1), 0) / holdings.length) * 15 * 100) / 100,
      beta: Math.round((holdings.reduce((sum, h) => sum + (h.beta || 1) * h.marketValue, 0) / holdings.reduce((sum, h) => sum + h.marketValue, 0)) * 100) / 100,
      correlation: Math.round(Math.random() * 0.3 + 0.6, 2)
    };
  };

  const generateStressTests = () => {
    return [
      { scenario: 'Market Crash (-20%)', impact: -0.20 },
      { scenario: 'Tech Selloff (-15%)', impact: -0.12 },
      { scenario: 'Interest Rate Rise', impact: -0.08 },
      { scenario: 'Inflation Surge', impact: -0.06 },
      { scenario: 'Recession', impact: -0.25 }
    ];
  };

  // Show loading state while authentication is being checked
  if (isLoading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  // Don't render anything if not authenticated (will redirect)
  if (!isAuthenticated) {
    return null;
  }
  
  const [addHoldingDialog, setAddHoldingDialog] = useState(false);
  const [orderBy, setOrderBy] = useState('allocation');
  const [order, setOrder] = useState('desc');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [timeframe, setTimeframe] = useState('1Y');
  const [riskToggle, setRiskToggle] = useState('standard');
  const [riskSubTab, setRiskSubTab] = useState(0);
  const [riskAlertDialogOpen, setRiskAlertDialogOpen] = useState(false);
  const [newRiskAlert, setNewRiskAlert] = useState({
    symbol: '',
    metric: 'volatility',
    threshold: 25,
    condition: 'above'
  });

  // Advanced portfolio metrics calculations
  const portfolioMetrics = useMemo(() => {
    const { holdings } = portfolioData;
    const totalValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
    const totalCost = holdings.reduce((sum, h) => sum + (h.avgCost * h.shares), 0);
    const totalGainLoss = totalValue - totalCost;
    const totalGainLossPercent = ((totalValue - totalCost) / totalCost) * 100;

    // Calculate risk metrics
    const volatility = calculatePortfolioVolatility(holdings);
    const sharpeRatio = calculateSharpeRatio(totalGainLossPercent, volatility);
    const beta = calculatePortfolioBeta(holdings);
    const var95 = calculateVaR(holdings, 0.95);
    const maxDrawdown = calculateMaxDrawdown(portfolioData.performanceHistory);

    return {
      totalValue,
      totalCost,
      totalGainLoss,
      totalGainLossPercent,
      volatility,
      sharpeRatio,
      beta,
      var95,
      maxDrawdown,
      treynorRatio: totalGainLossPercent / beta,
      informationRatio: calculateInformationRatio(portfolioData.performanceHistory),
      calmarRatio: totalGainLossPercent / Math.abs(maxDrawdown)
    };
  }, [portfolioData]);

  // Factor analysis calculations
  const factorAnalysis = useMemo(() => {
    return calculateFactorExposure(portfolioData.holdings);
  }, [portfolioData.holdings]);

  // Sector and geographic diversification
  const diversificationMetrics = useMemo(() => {
    return {
      sectorConcentration: calculateConcentrationRisk(portfolioData.sectorAllocation),
      geographicDiversification: calculateGeographicDiversification(portfolioData.holdings),
      marketCapExposure: calculateMarketCapExposure(portfolioData.holdings),
      concentrationRisk: calculateHerfindahlIndex(portfolioData.holdings)
    };
  }, [portfolioData]);

  // AI-powered insights
  const aiInsights = useMemo(() => {
    return generateAIInsights(portfolioMetrics, factorAnalysis, diversificationMetrics);
  }, [portfolioMetrics, factorAnalysis, diversificationMetrics]);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handleSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
  };

  const sortedHoldings = useMemo(() => {
    return portfolioData.holdings.sort((a, b) => {
      const aValue = a[orderBy];
      const bValue = b[orderBy];
      
      if (order === 'asc') {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      } else {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
      }
    });
  }, [portfolioData.holdings, orderBy, order]);

  if (isLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Portfolio Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Portfolio Analytics
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Institutional-grade portfolio analysis and risk management
          </Typography>
          {user && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              Welcome back, {user.firstName || user.username} • Last updated: {new Date(portfolioData.lastUpdated).toLocaleString()}
            </Typography>
          )}
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={timeframe}
              label="Timeframe"
              onChange={(e) => setTimeframe(e.target.value)}
            >
              <MenuItem value="1D">1 Day</MenuItem>
              <MenuItem value="1W">1 Week</MenuItem>
              <MenuItem value="1M">1 Month</MenuItem>
              <MenuItem value="3M">3 Months</MenuItem>
              <MenuItem value="1Y">1 Year</MenuItem>
              <MenuItem value="3Y">3 Years</MenuItem>
            </Select>
          </FormControl>
          <Button variant="outlined" startIcon={<Download />}>
            Export
          </Button>
          <Button variant="contained" startIcon={<Add />}>
            Add Position
          </Button>
        </Box>
      </Box>

      {/* Key Metrics Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Total Value
                  </Typography>
                  <Typography variant="h4" color="primary">
                    {formatCurrency(portfolioMetrics.totalValue)}
                  </Typography>
                  <Box display="flex" alignItems="center" mt={1}>
                    {portfolioMetrics.totalGainLossPercent >= 0 ? (
                      <TrendingUp color="success" fontSize="small" />
                    ) : (
                      <TrendingDown color="error" fontSize="small" />
                    )}
                    <Typography 
                      variant="body2" 
                      color={portfolioMetrics.totalGainLossPercent >= 0 ? 'success.main' : 'error.main'}
                      ml={0.5}
                    >
                      {formatCurrency(portfolioMetrics.totalGainLoss)} ({formatPercentage(portfolioMetrics.totalGainLossPercent)})
                    </Typography>
                  </Box>
                </Box>
                <AccountBalanceWallet color="primary" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Sharpe Ratio
                  </Typography>
                  <Typography variant="h4" color="secondary">
                    {formatNumber(portfolioMetrics.sharpeRatio, 2)}
                  </Typography>
                  <Rating 
                    value={Math.min(5, Math.max(0, portfolioMetrics.sharpeRatio))} 
                    readOnly 
                    size="small"
                    sx={{ mt: 1 }}
                  />
                </Box>
                <Assessment color="secondary" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Portfolio Beta
                  </Typography>
                  <Typography variant="h4" color="info.main">
                    {formatNumber(portfolioMetrics.beta, 2)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {portfolioMetrics.beta > 1 ? 'Higher volatility' : 'Lower volatility'}
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
                  <Typography variant="h6" color="text.secondary">
                    VaR (95%)
                  </Typography>
                  <Typography variant="h4" color="warning.main">
                    {formatCurrency(portfolioMetrics.var95)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Maximum 1-day loss
                  </Typography>
                </Box>
                <Shield color="warning" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Main Content Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="portfolio tabs" variant="scrollable" scrollButtons="auto">
          <Tab label="Holdings" icon={<AccountBalance />} />
          <Tab label="Performance" icon={<Timeline />} />
          <Tab label="Factor Analysis" icon={<Analytics />} />
          <Tab label="Risk Management" icon={<Security />} />
          <Tab label="AI Insights" icon={<Psychology />} />
          <Tab label="Optimization" icon={<Lightbulb />} />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        {/* Holdings Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader 
                title="Portfolio Holdings" 
                action={
                  <Chip 
                    label={`${portfolioData.holdings.length} positions`} 
                    color="primary" 
                    variant="outlined" 
                  />
                }
              />
              <CardContent>
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>
                          <TableSortLabel
                            active={orderBy === 'symbol'}
                            direction={orderBy === 'symbol' ? order : 'asc'}
                            onClick={() => handleSort('symbol')}
                          >
                            Symbol
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === 'shares'}
                            direction={orderBy === 'shares' ? order : 'asc'}
                            onClick={() => handleSort('shares')}
                          >
                            Shares
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === 'avgCost'}
                            direction={orderBy === 'avgCost' ? order : 'asc'}
                            onClick={() => handleSort('avgCost')}
                          >
                            Avg Cost
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">Current Price</TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === 'marketValue'}
                            direction={orderBy === 'marketValue' ? order : 'asc'}
                            onClick={() => handleSort('marketValue')}
                          >
                            Market Value
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === 'gainLossPercent'}
                            direction={orderBy === 'gainLossPercent' ? order : 'asc'}
                            onClick={() => handleSort('gainLossPercent')}
                          >
                            Gain/Loss
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="right">
                          <TableSortLabel
                            active={orderBy === 'allocation'}
                            direction={orderBy === 'allocation' ? order : 'asc'}
                            onClick={() => handleSort('allocation')}
                          >
                            Allocation
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {sortedHoldings
                        .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                        .map((holding) => (
                        <TableRow key={holding.symbol}>
                          <TableCell>
                            <Box>
                              <Typography variant="subtitle2" fontWeight="bold">
                                {holding.symbol}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {holding.company}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            {formatNumber(holding.shares)}
                          </TableCell>
                          <TableCell align="right">
                            {formatCurrency(holding.avgCost)}
                          </TableCell>
                          <TableCell align="right">
                            {formatCurrency(holding.currentPrice)}
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontWeight="bold">
                              {formatCurrency(holding.marketValue)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Box>
                              <Typography 
                                variant="body2" 
                                color={holding.gainLossPercent >= 0 ? 'success.main' : 'error.main'}
                                fontWeight="bold"
                              >
                                {formatCurrency(holding.gainLoss)}
                              </Typography>
                              <Chip
                                label={`${holding.gainLossPercent >= 0 ? '+' : ''}${formatPercentage(holding.gainLossPercent)}`}
                                color={holding.gainLossPercent >= 0 ? 'success' : 'error'}
                                size="small"
                                variant="outlined"
                              />
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            <Box>
                              <Typography variant="body2">
                                {formatPercentage(holding.allocation)}
                              </Typography>
                              <LinearProgress 
                                variant="determinate" 
                                value={holding.allocation} 
                                sx={{ mt: 0.5, width: 60 }}
                              />
                            </Box>
                          </TableCell>
                          <TableCell align="center">
                            <IconButton size="small" color="primary">
                              <Edit />
                            </IconButton>
                            <IconButton size="small" color="error">
                              <Delete />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                <TablePagination
                  rowsPerPageOptions={[10, 25, 50]}
                  component="div"
                  count={portfolioData.holdings.length}
                  rowsPerPage={rowsPerPage}
                  page={page}
                  onPageChange={(e, newPage) => setPage(newPage)}
                  onRowsPerPageChange={(e) => setRowsPerPage(parseInt(e.target.value, 10))}
                />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* Allocation Charts */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Asset Allocation" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={portfolioData.sectorAllocation}
                          cx="50%"
                          cy="50%"
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="value"
                          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                        >
                          {portfolioData.sectorAllocation.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <RechartsTooltip formatter={(value) => [formatPercentage(value), 'Allocation']} />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>

              {/* Concentration Risk */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Concentration Analysis" />
                  <CardContent>
                    <Box mb={2}>
                      <Typography variant="body2" color="text.secondary">
                        Portfolio Concentration Risk
                      </Typography>
                      <LinearProgress 
                        variant="determinate" 
                        value={diversificationMetrics.concentrationRisk * 100} 
                        color={diversificationMetrics.concentrationRisk > 0.3 ? 'error' : 'success'}
                        sx={{ mt: 1 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        Herfindahl Index: {formatNumber(diversificationMetrics.concentrationRisk, 3)}
                      </Typography>
                    </Box>
                    
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Top 3 Holdings: {formatPercentage(
                        portfolioData.holdings
                          .sort((a, b) => b.allocation - a.allocation)
                          .slice(0, 3)
                          .reduce((sum, h) => sum + h.allocation, 0)
                      )}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        {/* Performance Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Portfolio Performance" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <ComposedChart data={portfolioData.performanceHistory}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis yAxisId="left" />
                    <YAxis yAxisId="right" orientation="right" />
                    <RechartsTooltip />
                    <Area 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="portfolioValue" 
                      fill="#8884d8" 
                      stroke="#8884d8"
                      fillOpacity={0.3}
                    />
                    <Line 
                      yAxisId="right"
                      type="monotone" 
                      dataKey="benchmarkValue" 
                      stroke="#82ca9d" 
                      strokeWidth={2}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* Performance Metrics */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Performance Metrics" />
                  <CardContent>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Sharpe Ratio</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.sharpeRatio, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Treynor Ratio</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.treynorRatio, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Information Ratio</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.informationRatio, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Calmar Ratio</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.calmarRatio, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Max Drawdown</Typography>
                        <Typography variant="body2" fontWeight="bold" color="error.main">
                          {formatPercentage(portfolioMetrics.maxDrawdown)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Volatility</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatPercentage(portfolioMetrics.volatility)}
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Benchmark Comparison */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="vs S&P 500" />
                  <CardContent>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Alpha</Typography>
                        <Chip 
                          label={formatPercentage(2.3)} 
                          color="success" 
                          size="small"
                        />
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Beta</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(portfolioMetrics.beta, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">R-Squared</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(0.87, 2)}
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Tracking Error</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatPercentage(4.2)}
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        {/* Factor Analysis Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Multi-Factor Exposure Analysis" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <RadarChart data={factorAnalysis}>
                    <PolarGrid />
                    <PolarAngleAxis dataKey="factor" />
                    <PolarRadiusAxis 
                      angle={90} 
                      domain={[-100, 100]} 
                      tick={{ fontSize: 12 }}
                    />
                    <Radar
                      name="Portfolio"
                      dataKey="exposure"
                      stroke="#8884d8"
                      fill="#8884d8"
                      fillOpacity={0.3}
                      strokeWidth={2}
                    />
                    <Radar
                      name="Benchmark"
                      dataKey="benchmark"
                      stroke="#82ca9d"
                      fill="transparent"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                    />
                    <RechartsTooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Factor Scores" />
              <CardContent>
                {factorAnalysis.map((factor) => (
                  <Box key={factor.factor} mb={3}>
                    <Box display="flex" justifyContent="between" mb={1}>
                      <Typography variant="body2" fontWeight="bold">
                        {factor.factor}
                      </Typography>
                      <Chip 
                        label={formatNumber(factor.exposure, 1)}
                        color={factor.exposure > 10 ? 'success' : factor.exposure < -10 ? 'error' : 'default'}
                        size="small"
                      />
                    </Box>
                    <LinearProgress 
                      variant="determinate" 
                      value={Math.min(100, Math.max(0, (factor.exposure + 100) / 2))}
                      color={factor.exposure > 0 ? 'success' : 'error'}
                      sx={{ mb: 1 }}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {factor.description}
                    </Typography>
                  </Box>
                ))}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        {/* Enhanced Risk Management Tab */}
        {/* Risk Summary Cards */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="text.secondary" gutterBottom>Portfolio VaR (95%)</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatCurrency(portfolioMetrics.var95)}
                    </Typography>
                  </Box>
                  <Security sx={{ fontSize: 40, color: 'primary.main' }} />
                </Box>
                <LinearProgress 
                  variant="determinate" 
                  value={(portfolioMetrics.var95 / portfolioMetrics.totalValue) * 100} 
                  sx={{ mt: 1 }}
                  color={(portfolioMetrics.var95 / portfolioMetrics.totalValue) * 100 <= 3 ? 'success' : (portfolioMetrics.var95 / portfolioMetrics.totalValue) * 100 <= 8 ? 'warning' : 'error'}
                />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="text.secondary" gutterBottom>Sharpe Ratio</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatNumber(portfolioMetrics.sharpeRatio, 2)}
                    </Typography>
                  </Box>
                  <Assessment sx={{ fontSize: 40, color: 'success.main' }} />
                </Box>
                <Chip 
                  label={portfolioMetrics.sharpeRatio > 1 ? 'Good' : 'Needs Improvement'} 
                  color={portfolioMetrics.sharpeRatio > 1 ? 'success' : 'warning'}
                  size="small"
                  sx={{ mt: 1 }}
                />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="text.secondary" gutterBottom>Portfolio Beta</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatNumber(portfolioMetrics.beta, 2)}
                    </Typography>
                  </Box>
                  <TrendingUp sx={{ fontSize: 40, color: 'info.main' }} />
                </Box>
                <Chip 
                  label={portfolioMetrics.beta > 1 ? 'High Risk' : 'Low Risk'} 
                  color={portfolioMetrics.beta > 1.2 ? 'error' : portfolioMetrics.beta > 0.8 ? 'warning' : 'success'}
                  size="small"
                  sx={{ mt: 1 }}
                />
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="text.secondary" gutterBottom>Max Drawdown</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {formatPercentage(portfolioMetrics.maxDrawdown)}
                    </Typography>
                  </Box>
                  <Warning sx={{ fontSize: 40, color: 'warning.main' }} />
                </Box>
                <LinearProgress 
                  variant="determinate" 
                  value={Math.abs(portfolioMetrics.maxDrawdown * 100)} 
                  sx={{ mt: 1 }}
                  color={Math.abs(portfolioMetrics.maxDrawdown) <= 0.1 ? 'success' : Math.abs(portfolioMetrics.maxDrawdown) <= 0.2 ? 'warning' : 'error'}
                />
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Risk Management Sub-tabs */}
        <Card>
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={riskSubTab} onChange={(e, v) => setRiskSubTab(v)} aria-label="risk management tabs">
              <Tab label="Position Risk" />
              <Tab label="VaR Analysis" />
              <Tab label="Stress Testing" />
              <Tab label="Risk Alerts" />
            </Tabs>
          </Box>

          <Box sx={{ p: 3 }}>
            {riskSubTab === 0 && (
              <Box>
                <Typography variant="h6" gutterBottom>Position Risk Analysis</Typography>
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Weight</TableCell>
                        <TableCell align="right">VaR (95%)</TableCell>
                        <TableCell align="right">Beta</TableCell>
                        <TableCell align="right">Volatility</TableCell>
                        <TableCell align="right">Risk Contribution</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {portfolioData.holdings.map((holding) => (
                        <TableRow key={holding.symbol}>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {holding.symbol}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="right">{formatPercentage(holding.weight)}</TableCell>
                          <TableCell align="right">{formatCurrency(holding.value * 0.05)}</TableCell>
                          <TableCell align="right">
                            <Chip 
                              label={formatNumber(holding.beta || 1.0, 2)} 
                              color={(holding.beta || 1.0) <= 0.8 ? 'success' : (holding.beta || 1.0) <= 1.2 ? 'warning' : 'error'}
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">
                            <Chip 
                              label={formatPercentage((holding.volatility || 0.2))} 
                              color={(holding.volatility || 0.2) <= 0.2 ? 'success' : (holding.volatility || 0.2) <= 0.3 ? 'warning' : 'error'}
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">
                            <LinearProgress 
                              variant="determinate" 
                              value={holding.weight * 100} 
                              sx={{ width: 60 }}
                              color={holding.weight <= 0.2 ? 'success' : holding.weight <= 0.3 ? 'warning' : 'error'}
                            />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            )}

            {riskSubTab === 1 && (
              <Box>
                <Typography variant="h6" gutterBottom>Value at Risk Trends</Typography>
                <Box sx={{ height: 400, mt: 2 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={portfolioData.historicalVaR || [
                      { date: '2025-06-28', var95: 65000, var99: 120000 },
                      { date: '2025-06-29', var95: 67000, var99: 122000 },
                      { date: '2025-06-30', var95: 66500, var99: 121000 },
                      { date: '2025-07-01', var95: 68000, var99: 124000 },
                      { date: '2025-07-02', var95: 68500, var99: 125000 }
                    ]}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip formatter={(value) => [`$${value.toLocaleString()}`, '']} />
                      <Line type="monotone" dataKey="var95" stroke="#1976d2" name="VaR 95%" strokeWidth={2} />
                      <Line type="monotone" dataKey="var99" stroke="#d32f2f" name="VaR 99%" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              </Box>
            )}

            {riskSubTab === 2 && (
              <Box>
                <Typography variant="h6" gutterBottom>Stress Test Results</Typography>
                <Grid container spacing={2}>
                  {portfolioData.stressTests.map((test, index) => (
                    <Grid item xs={12} md={6} key={index}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                            {test.scenario}
                          </Typography>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                            <Typography color="text.secondary">Potential Loss:</Typography>
                            <Typography sx={{ color: 'error.main', fontWeight: 600 }}>
                              ${Math.abs(test.impact * portfolioMetrics.totalValue).toLocaleString()} ({formatPercentage(Math.abs(test.impact))})
                            </Typography>
                          </Box>
                          <LinearProgress 
                            variant="determinate" 
                            value={Math.abs(test.impact * 100)} 
                            color="error"
                            sx={{ mt: 1 }}
                          />
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </Box>
            )}

            {riskSubTab === 3 && (
              <Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography variant="h6">Risk Alerts</Typography>
                  <Button variant="contained" startIcon={<Notifications />} onClick={() => setRiskAlertDialogOpen(true)}>
                    Create Alert
                  </Button>
                </Box>
                
                {mockRiskAlerts.map((alert) => (
                  <Alert 
                    key={alert.id} 
                    severity={alert.severity} 
                    sx={{ mb: 2 }}
                  >
                    <Typography variant="body2">
                      <strong>{alert.symbol}</strong> {alert.metric} is {alert.value}{typeof alert.value === 'number' && alert.value < 10 ? '' : '%'} 
                      (threshold: {alert.threshold}{typeof alert.threshold === 'number' && alert.threshold < 10 ? '' : '%'})
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {new Date(alert.timestamp).toLocaleString()}
                    </Typography>
                  </Alert>
                ))}
              </Box>
            )}
          </Box>
        </Card>
      </TabPanel>

      <TabPanel value={activeTab} index={4}>
        {/* AI Insights Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader 
                title="AI-Powered Portfolio Analysis" 
                avatar={<Psychology color="primary" />}
              />
              <CardContent>
                <Stepper orientation="vertical">
                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="success.main">
                        Strengths Identified
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <List>
                        {aiInsights.strengths.map((strength, index) => (
                          <ListItem key={index}>
                            <CheckCircle color="success" sx={{ mr: 2 }} />
                            <Typography variant="body2">{strength}</Typography>
                          </ListItem>
                        ))}
                      </List>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="warning.main">
                        Improvement Opportunities
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <List>
                        {aiInsights.improvements.map((improvement, index) => (
                          <ListItem key={index}>
                            <Lightbulb color="warning" sx={{ mr: 2 }} />
                            <Typography variant="body2">{improvement}</Typography>
                          </ListItem>
                        ))}
                      </List>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="info.main">
                        Market Analysis
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <Alert severity="info" sx={{ mt: 1 }}>
                        {aiInsights.marketAnalysis}
                      </Alert>
                    </StepContent>
                  </Step>
                </Stepper>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="AI Confidence Score" />
              <CardContent>
                <Box textAlign="center" mb={3}>
                  <Typography variant="h2" color="primary">
                    {aiInsights.confidenceScore}%
                  </Typography>
                  <Rating 
                    value={aiInsights.confidenceScore / 20} 
                    readOnly 
                    size="large"
                  />
                  <Typography variant="body2" color="text.secondary">
                    Analysis Confidence
                  </Typography>
                </Box>
                
                <Divider sx={{ my: 2 }} />
                
                <Typography variant="subtitle2" gutterBottom>
                  Key Recommendations
                </Typography>
                {aiInsights.recommendations.map((rec, index) => (
                  <Chip
                    key={index}
                    label={rec}
                    variant="outlined"
                    size="small"
                    sx={{ m: 0.5 }}
                  />
                ))}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={5}>
        {/* Optimization Tab */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Portfolio Optimization" />
              <CardContent>
                <Alert severity="info" sx={{ mb: 3 }}>
                  Advanced portfolio optimization tools including mean-variance optimization, 
                  Black-Litterman model, and risk parity strategies.
                </Alert>
                
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="h6" gutterBottom>
                      Optimization Objectives
                    </Typography>
                    <FormControl fullWidth sx={{ mb: 2 }}>
                      <InputLabel>Optimization Method</InputLabel>
                      <Select defaultValue="sharpe">
                        <MenuItem value="sharpe">Maximize Sharpe Ratio</MenuItem>
                        <MenuItem value="return">Maximize Return</MenuItem>
                        <MenuItem value="risk">Minimize Risk</MenuItem>
                        <MenuItem value="blacklitterman">Black-Litterman</MenuItem>
                        <MenuItem value="riskparity">Risk Parity</MenuItem>
                      </Select>
                    </FormControl>
                    
                    <Typography variant="body2" gutterBottom>
                      Risk Tolerance
                    </Typography>
                    <Slider
                      defaultValue={50}
                      step={10}
                      marks
                      min={0}
                      max={100}
                      valueLabelDisplay="auto"
                      sx={{ mb: 3 }}
                    />
                  </Grid>
                  
                  <Grid item xs={12} md={6}>
                    <Typography variant="h6" gutterBottom>
                      Constraints
                    </Typography>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <FormControlLabel
                        control={<Switch defaultChecked />}
                        label="Sector diversification limits"
                      />
                      <FormControlLabel
                        control={<Switch defaultChecked />}
                        label="Maximum position size (10%)"
                      />
                      <FormControlLabel
                        control={<Switch />}
                        label="ESG constraints"
                      />
                      <FormControlLabel
                        control={<Switch />}
                        label="Transaction cost optimization"
                      />
                    </Box>
                  </Grid>
                </Grid>
                
                <Box mt={3}>
                  <Button variant="contained" size="large" startIcon={<Analytics />}>
                    Run Optimization
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Risk Alert Dialog */}
      <Dialog open={riskAlertDialogOpen} onClose={() => setRiskAlertDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Risk Alert</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Symbol"
                value={newRiskAlert.symbol}
                onChange={(e) => setNewRiskAlert({ ...newRiskAlert, symbol: e.target.value })}
                placeholder="e.g., AAPL or PORTFOLIO"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Metric</InputLabel>
                <Select
                  value={newRiskAlert.metric}
                  onChange={(e) => setNewRiskAlert({ ...newRiskAlert, metric: e.target.value })}
                  label="Metric"
                >
                  <MenuItem value="volatility">Volatility</MenuItem>
                  <MenuItem value="beta">Beta</MenuItem>
                  <MenuItem value="var">Value at Risk</MenuItem>
                  <MenuItem value="concentration">Concentration</MenuItem>
                  <MenuItem value="correlation">Correlation</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>Condition</InputLabel>
                <Select
                  value={newRiskAlert.condition}
                  onChange={(e) => setNewRiskAlert({ ...newRiskAlert, condition: e.target.value })}
                  label="Condition"
                >
                  <MenuItem value="above">Above</MenuItem>
                  <MenuItem value="below">Below</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="Threshold"
                type="number"
                value={newRiskAlert.threshold}
                onChange={(e) => setNewRiskAlert({ ...newRiskAlert, threshold: Number(e.target.value) })}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRiskAlertDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={() => {
              console.log('Creating risk alert:', newRiskAlert);
              setRiskAlertDialogOpen(false);
              setNewRiskAlert({
                symbol: '',
                metric: 'volatility',
                threshold: 25,
                condition: 'above'
              });
            }} 
            variant="contained"
          >
            Create Alert
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

// Enhanced mock data with realistic portfolio metrics
const mockPortfolioData = {
  holdings: [
    {
      symbol: 'AAPL',
      company: 'Apple Inc.',
      shares: 100,
      avgCost: 150.00,
      currentPrice: 189.45,
      marketValue: 18945,
      gainLoss: 3945,
      gainLossPercent: 26.30,
      sector: 'Technology',
      allocation: 23.5,
      beta: 1.2,
      factorScores: { quality: 85, growth: 60, value: 25, momentum: 75, sentiment: 70, positioning: 45 }
    },
    {
      symbol: 'MSFT',
      company: 'Microsoft Corporation',
      shares: 50,
      avgCost: 300.00,
      currentPrice: 342.56,
      marketValue: 17128,
      gainLoss: 2128,
      gainLossPercent: 14.19,
      sector: 'Technology',
      allocation: 21.3,
      beta: 0.9,
      factorScores: { quality: 90, growth: 65, value: 30, momentum: 80, sentiment: 75, positioning: 50 }
    },
    {
      symbol: 'GOOGL',
      company: 'Alphabet Inc.',
      shares: 25,
      avgCost: 120.00,
      currentPrice: 134.23,
      marketValue: 3356,
      gainLoss: 356,
      gainLossPercent: 11.86,
      sector: 'Technology',
      allocation: 4.2,
      beta: 1.1,
      factorScores: { quality: 80, growth: 70, value: 40, momentum: 65, sentiment: 60, positioning: 35 }
    },
    {
      symbol: 'JNJ',
      company: 'Johnson & Johnson',
      shares: 75,
      avgCost: 160.00,
      currentPrice: 156.78,
      marketValue: 11759,
      gainLoss: -241,
      gainLossPercent: -2.01,
      sector: 'Healthcare',
      allocation: 14.6,
      beta: 0.7,
      factorScores: { quality: 95, growth: 25, value: 60, momentum: 30, sentiment: 45, positioning: 65 }
    },
    {
      symbol: 'JPM',
      company: 'JPMorgan Chase & Co.',
      shares: 60,
      avgCost: 140.00,
      currentPrice: 167.89,
      marketValue: 10073,
      gainLoss: 1673,
      gainLossPercent: 19.89,
      sector: 'Financials',
      allocation: 12.5,
      beta: 1.3,
      factorScores: { quality: 75, growth: 40, value: 70, momentum: 55, sentiment: 50, positioning: 60 }
    },
    {
      symbol: 'PG',
      company: 'Procter & Gamble Co.',
      shares: 40,
      avgCost: 145.00,
      currentPrice: 153.21,
      marketValue: 6128,
      gainLoss: 328,
      gainLossPercent: 5.66,
      sector: 'Consumer Staples',
      allocation: 7.6,
      beta: 0.5,
      factorScores: { quality: 85, growth: 20, value: 45, momentum: 25, sentiment: 55, positioning: 70 }
    },
    {
      symbol: 'BRK.B',
      company: 'Berkshire Hathaway Inc.',
      shares: 30,
      avgCost: 320.00,
      currentPrice: 345.67,
      marketValue: 10370,
      gainLoss: 770,
      gainLossPercent: 8.01,
      sector: 'Financials',
      allocation: 12.9,
      beta: 0.8,
      factorScores: { quality: 90, growth: 35, value: 80, momentum: 40, sentiment: 60, positioning: 75 }
    },
    {
      symbol: 'V',
      company: 'Visa Inc.',
      shares: 35,
      avgCost: 200.00,
      currentPrice: 234.56,
      marketValue: 8210,
      gainLoss: 1210,
      gainLossPercent: 17.29,
      sector: 'Financials',
      allocation: 10.2,
      beta: 1.0,
      factorScores: { quality: 85, growth: 55, value: 35, momentum: 70, sentiment: 65, positioning: 55 }
    }
  ],
  sectorAllocation: [
    { name: 'Technology', value: 48.9 },
    { name: 'Financials', value: 25.6 },
    { name: 'Healthcare', value: 14.6 },
    { name: 'Consumer Staples', value: 7.6 },
    { name: 'Others', value: 3.3 }
  ],
  performanceHistory: Array.from({ length: 365 }, (_, i) => ({
    date: new Date(Date.now() - (365 - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    portfolioValue: 75000 + Math.random() * 15000 + i * 20,
    benchmarkValue: 75000 + Math.random() * 12000 + i * 18
  })),
  stressTests: [
    { scenario: '2008 Financial Crisis', impact: -37.2 },
    { scenario: 'COVID-19 Crash', impact: -22.8 },
    { scenario: 'Tech Bubble Burst', impact: -28.5 },
    { scenario: 'Interest Rate Shock', impact: -15.3 },
    { scenario: 'Inflation Spike', impact: -12.7 },
    { scenario: 'Geopolitical Crisis', impact: -18.9 }
  ]
};

// Mock risk alerts data
const mockRiskAlerts = [
  { id: 1, symbol: 'AAPL', metric: 'Volatility', value: 28.2, threshold: 25, severity: 'medium', timestamp: '2025-07-03T10:30:00Z' },
  { id: 2, symbol: 'PORTFOLIO', metric: 'Concentration', value: 48, threshold: 40, severity: 'high', timestamp: '2025-07-03T09:15:00Z' },
  { id: 3, symbol: 'JPM', metric: 'Beta', value: 1.3, threshold: 1.2, severity: 'medium', timestamp: '2025-07-03T08:45:00Z' },
  { id: 4, symbol: 'MSFT', metric: 'VaR', value: 5.2, threshold: 5.0, severity: 'low', timestamp: '2025-07-02T16:20:00Z' }
];

// Color palette for charts
const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

// Helper functions for calculations
function calculatePortfolioVolatility(holdings) {
  // Simplified calculation - in reality, this would use historical returns and correlations
  const weightedVolatilities = holdings.map(h => (h.allocation / 100) * (h.beta * 16)); // Assuming market vol of 16%
  return Math.sqrt(weightedVolatilities.reduce((sum, vol) => sum + vol * vol, 0));
}

function calculateSharpeRatio(return_, volatility) {
  const riskFreeRate = 2.5; // Assume 2.5% risk-free rate
  return (return_ - riskFreeRate) / volatility;
}

function calculatePortfolioBeta(holdings) {
  return holdings.reduce((sum, h) => sum + (h.allocation / 100) * h.beta, 0);
}

function calculateVaR(holdings, confidence) {
  const portfolioValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
  const portfolioVol = calculatePortfolioVolatility(holdings) / 100;
  const zScore = confidence === 0.95 ? 1.645 : 2.326; // 95% or 99%
  return portfolioValue * portfolioVol * zScore / Math.sqrt(252); // Daily VaR
}

function calculateMaxDrawdown(performanceHistory) {
  let maxDrawdown = 0;
  let peak = performanceHistory[0].portfolioValue;
  
  for (let point of performanceHistory) {
    if (point.portfolioValue > peak) {
      peak = point.portfolioValue;
    }
    const drawdown = (peak - point.portfolioValue) / peak;
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown;
    }
  }
  
  return maxDrawdown * 100; // Return as percentage
}

function calculateInformationRatio(performanceHistory) {
  // Simplified calculation
  const excessReturns = performanceHistory.map(p => 
    (p.portfolioValue / performanceHistory[0].portfolioValue - 1) - 
    (p.benchmarkValue / performanceHistory[0].benchmarkValue - 1)
  );
  const avgExcessReturn = excessReturns.reduce((sum, ret) => sum + ret, 0) / excessReturns.length;
  const trackingError = Math.sqrt(excessReturns.reduce((sum, ret) => sum + Math.pow(ret - avgExcessReturn, 2), 0) / excessReturns.length);
  return avgExcessReturn / trackingError * Math.sqrt(252); // Annualized
}

function calculateFactorExposure(holdings) {
  const factors = ['Quality', 'Growth', 'Value', 'Momentum', 'Sentiment', 'Positioning'];
  return factors.map(factor => {
    const exposure = holdings.reduce((sum, h) => {
      const factorKey = factor.toLowerCase();
      return sum + (h.allocation / 100) * (h.factorScores[factorKey] - 50); // Center around 50
    }, 0);
    
    return {
      factor,
      exposure,
      benchmark: 0, // Benchmark is neutral (0)
      description: getFactorDescription(factor)
    };
  });
}

function getFactorDescription(factor) {
  const descriptions = {
    'Quality': 'Companies with strong fundamentals, high ROE, low debt',
    'Growth': 'Companies with strong revenue and earnings growth',
    'Value': 'Undervalued companies with attractive valuations',
    'Momentum': 'Stocks with positive price and earnings momentum',
    'Sentiment': 'Stocks with positive analyst and market sentiment',
    'Positioning': 'Stocks with favorable institutional positioning'
  };
  return descriptions[factor] || '';
}

function calculateConcentrationRisk(sectorAllocation) {
  // Herfindahl-Hirschman Index
  return sectorAllocation.reduce((sum, sector) => sum + Math.pow(sector.value / 100, 2), 0);
}

function calculateGeographicDiversification(holdings) {
  // Simplified - assume all holdings are US for now
  return { US: 100, International: 0, Emerging: 0 };
}

function calculateMarketCapExposure(holdings) {
  // Simplified categorization
  return {
    LargeCap: 75.5,
    MidCap: 20.3,
    SmallCap: 4.2
  };
}

function calculateHerfindahlIndex(holdings) {
  const totalValue = holdings.reduce((sum, h) => sum + h.marketValue, 0);
  return holdings.reduce((sum, h) => sum + Math.pow(h.marketValue / totalValue, 2), 0);
}

function generateAIInsights(portfolioMetrics, factorAnalysis, diversificationMetrics) {
  return {
    confidenceScore: 87,
    strengths: [
      `Strong risk-adjusted returns with Sharpe ratio of ${formatNumber(portfolioMetrics.sharpeRatio, 2)}`,
      'Well-diversified across sectors with controlled concentration risk',
      'Quality factor exposure provides downside protection',
      'Portfolio beta of ' + formatNumber(portfolioMetrics.beta, 2) + ' offers balanced market exposure'
    ],
    improvements: [
      'Consider increasing international diversification',
      'Value factor exposure could be enhanced for rotation opportunities',
      'Technology concentration warrants monitoring',
      'ESG integration could improve long-term sustainability'
    ],
    marketAnalysis: 'Current market environment favors quality and momentum factors. Portfolio positioning aligns well with institutional trends while maintaining defensive characteristics through healthcare and consumer staples exposure.',
    recommendations: ['Rebalance Technology', 'Add International', 'Increase Value', 'Monitor Risk']
  };
}

export default Portfolio;