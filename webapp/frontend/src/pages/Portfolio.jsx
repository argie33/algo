import React, { useState, useEffect } from 'react';
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
  TablePagination
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
  Scatter
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
  Settings,
  ExpandMore,
  Report,
  Speed,
  BusinessCenter
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
  const [portfolioData, setPortfolioData] = useState({
    holdings: [],
    totalValue: 0,
    totalGainLoss: 0,
    totalGainLossPercent: 0,
    assetAllocation: [],
    sectorAllocation: [],
    riskMetrics: {},
    riskAlerts: [],
    riskLimits: {},
    stressTests: [],
    correlationMatrix: []
  });
  const [loading, setLoading] = useState(false);
  const [addHoldingDialog, setAddHoldingDialog] = useState(false);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [newHolding, setNewHolding] = useState({
    symbol: '',
    shares: '',
    avgCost: '',
    currentPrice: ''
  });
  const [newAlert, setNewAlert] = useState({
    type: 'portfolio_loss',
    threshold: '',
    condition: 'greater_than',
    enabled: true
  });
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // Combined mock data for portfolio, analysis, and risk management
  const mockPortfolioData = {
    holdings: [
      {
        symbol: 'AAPL',
        company: 'Apple Inc.',
        shares: 100,
        avgCost: 150.00,
        currentPrice: 175.43,
        marketValue: 17543,
        gainLoss: 2543,
        gainLossPercent: 16.95,
        sector: 'Technology',
        allocation: 35.2
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
        allocation: 34.4
      },
      {
        symbol: 'GOOGL',
        company: 'Alphabet Inc.',
        shares: 75,
        avgCost: 120.00,
        currentPrice: 138.45,
        marketValue: 10384,
        gainLoss: 1384,
        gainLossPercent: 15.38,
        sector: 'Technology',
        allocation: 20.9
      },
      {
        symbol: 'JNJ',
        company: 'Johnson & Johnson',
        shares: 30,
        avgCost: 160.00,
        currentPrice: 155.78,
        marketValue: 4673,
        gainLoss: -127,
        gainLossPercent: -2.64,
        sector: 'Healthcare',
        allocation: 9.4
      }
    ],
    totalValue: 49728,
    totalGainLoss: 5928,
    totalGainLossPercent: 13.53,
    assetAllocation: [
      { name: 'Large Cap Growth', value: 70.1, color: '#1976d2' },
      { name: 'Large Cap Value', value: 20.5, color: '#43a047' },
      { name: 'Healthcare', value: 9.4, color: '#ff9800' }
    ],
    sectorAllocation: [
      { name: 'Technology', value: 90.5, color: '#1976d2' },
      { name: 'Healthcare', value: 9.4, color: '#43a047' },
      { name: 'Cash', value: 0.1, color: '#757575' }
    ],
    riskMetrics: {
      currentVaR: -2534.67,
      expectedShortfall: -3876.23,
      beta: 1.15,
      sharpeRatio: 0.87,
      sortino: 1.23,
      maxDrawdown: -12.34,
      volatility: 18.5,
      correlation: 0.92,
      riskLevel: 'Moderate High'
    },
    riskAlerts: [
      {
        id: 1,
        type: 'High Volatility',
        message: 'Portfolio volatility has exceeded 20%',
        severity: 'warning',
        timestamp: '2025-07-02T10:30:00Z',
        active: true
      },
      {
        id: 2,
        type: 'Concentration Risk',
        message: 'Technology sector allocation exceeds 70%',
        severity: 'error',
        timestamp: '2025-07-02T09:15:00Z',
        active: true
      }
    ],
    riskLimits: {
      maxPortfolioLoss: 10,
      maxSectorConcentration: 40,
      maxSinglePosition: 15,
      maxBeta: 1.3,
      maxVolatility: 25,
      minCash: 5
    },
    stressTests: [
      {
        scenario: '2008 Financial Crisis',
        portfolioImpact: -34.5,
        timeframe: '12 months',
        probability: 'Low'
      },
      {
        scenario: 'Tech Crash (2000)',
        portfolioImpact: -28.7,
        timeframe: '18 months',
        probability: 'Medium'
      },
      {
        scenario: 'COVID-19 Pandemic',
        portfolioImpact: -22.1,
        timeframe: '3 months',
        probability: 'Low'
      },
      {
        scenario: 'Interest Rate Shock',
        portfolioImpact: -15.3,
        timeframe: '6 months',
        probability: 'Medium'
      }
    ],
    correlationMatrix: [
      { asset: 'AAPL', correlation: 1.0, risk: 'Low' },
      { asset: 'MSFT', correlation: 0.78, risk: 'Medium' },
      { asset: 'GOOGL', correlation: 0.82, risk: 'Medium' },
      { asset: 'SPY', correlation: 0.92, risk: 'High' }
    ]
  };

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/');
      return;
    }
    if (isAuthenticated && tokens) {
      loadPortfolioData();
    }
  }, [isAuthenticated, isLoading, tokens, navigate]);

  const loadPortfolioData = async () => {
    if (!isAuthenticated || !tokens) {
      console.warn('User not authenticated, cannot load portfolio data');
      return;
    }

    setLoading(true);
    try {
      // Create headers with authentication
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${tokens.accessToken || tokens.idToken}`
      };

      // Try to fetch from authenticated API endpoint
      const response = await fetch(`${API_BASE}/api/portfolio/analytics`, {
        headers
      });
      
      if (response.ok) {
        const data = await response.json();
        setPortfolioData(data.data || data);
      } else if (response.status === 401) {
        console.error('Authentication failed, redirecting to login');
        navigate('/');
        return;
      } else {
        console.warn('Portfolio API failed, using mock data');
        setPortfolioData(mockPortfolioData);
      }
    } catch (error) {
      console.error('Failed to load portfolio data:', error);
      setPortfolioData(mockPortfolioData);
    } finally {
      setLoading(false);
    }
  };

  const addHolding = async () => {
    if (!newHolding.symbol || !newHolding.shares || !newHolding.avgCost) return;

    try {
      const shares = parseFloat(newHolding.shares);
      const avgCost = parseFloat(newHolding.avgCost);
      const currentPrice = parseFloat(newHolding.currentPrice) || avgCost;
      const marketValue = shares * currentPrice;
      const costBasis = shares * avgCost;
      const gainLoss = marketValue - costBasis;
      const gainLossPercent = (gainLoss / costBasis) * 100;

      const holding = {
        symbol: newHolding.symbol.toUpperCase(),
        company: `${newHolding.symbol.toUpperCase()} Corporation`,
        shares,
        avgCost,
        currentPrice,
        marketValue,
        gainLoss,
        gainLossPercent,
        sector: 'Unknown',
        allocation: 0
      };

      const newHoldings = [...portfolioData.holdings, holding];
      const newTotalValue = newHoldings.reduce((sum, h) => sum + h.marketValue, 0);
      
      newHoldings.forEach(h => {
        h.allocation = (h.marketValue / newTotalValue) * 100;
      });

      setPortfolioData(prev => ({
        ...prev,
        holdings: newHoldings,
        totalValue: newTotalValue,
        totalGainLoss: newHoldings.reduce((sum, h) => sum + h.gainLoss, 0),
        totalGainLossPercent: ((newTotalValue - newHoldings.reduce((sum, h) => sum + h.shares * h.avgCost, 0)) / newHoldings.reduce((sum, h) => sum + h.shares * h.avgCost, 0)) * 100
      }));

      setAddHoldingDialog(false);
      setNewHolding({ symbol: '', shares: '', avgCost: '', currentPrice: '' });
    } catch (error) {
      console.error('Failed to add holding:', error);
    }
  };

  const removeHolding = (symbol) => {
    const newHoldings = portfolioData.holdings.filter(h => h.symbol !== symbol);
    const newTotalValue = newHoldings.reduce((sum, h) => sum + h.marketValue, 0);
    
    newHoldings.forEach(h => {
      h.allocation = newTotalValue > 0 ? (h.marketValue / newTotalValue) * 100 : 0;
    });

    setPortfolioData(prev => ({
      ...prev,
      holdings: newHoldings,
      totalValue: newTotalValue,
      totalGainLoss: newHoldings.reduce((sum, h) => sum + h.gainLoss, 0),
      totalGainLossPercent: newTotalValue > 0 ? ((newTotalValue - newHoldings.reduce((sum, h) => sum + h.shares * h.avgCost, 0)) / newHoldings.reduce((sum, h) => sum + h.shares * h.avgCost, 0)) * 100 : 0
    }));
  };

  const createAlert = async () => {
    if (!newAlert.threshold) return;

    const alert = {
      id: Date.now(),
      type: newAlert.type,
      threshold: parseFloat(newAlert.threshold),
      condition: newAlert.condition,
      enabled: newAlert.enabled,
      created: new Date().toISOString()
    };

    setPortfolioData(prev => ({
      ...prev,
      riskAlerts: [...prev.riskAlerts, {
        id: alert.id,
        type: alert.type,
        message: `${alert.type} alert set for ${alert.threshold}%`,
        severity: 'info',
        timestamp: alert.created,
        active: alert.enabled
      }]
    }));

    setAlertDialogOpen(false);
    setNewAlert({ type: 'portfolio_loss', threshold: '', condition: 'greater_than', enabled: true });
  };

  const dismissAlert = (alertId) => {
    setPortfolioData(prev => ({
      ...prev,
      riskAlerts: prev.riskAlerts.map(alert => 
        alert.id === alertId ? { ...alert, active: false } : alert
      )
    }));
  };

  const exportPortfolio = () => {
    const csv = [
      ['Symbol', 'Company', 'Shares', 'Avg Cost', 'Current Price', 'Market Value', 'Gain/Loss', 'Gain/Loss %', 'Allocation %'],
      ...portfolioData.holdings.map(holding => [
        holding.symbol,
        holding.company,
        holding.shares,
        holding.avgCost,
        holding.currentPrice,
        holding.marketValue,
        holding.gainLoss,
        holding.gainLossPercent.toFixed(2),
        holding.allocation.toFixed(2)
      ])
    ].map(row => row.join(',')).join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'portfolio_comprehensive.csv';
    a.click();
  };

  const getGainLossColor = (value) => {
    if (value > 0) return 'success.main';
    if (value < 0) return 'error.main';
    return 'text.secondary';
  };

  const getRiskColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'low': return 'success';
      case 'medium': return 'warning';
      case 'high': return 'error';
      default: return 'primary';
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'error': return 'error';
      case 'warning': return 'warning';
      case 'info': return 'info';
      default: return 'primary';
    }
  };

  // Show loading spinner while auth is being checked
  if (isLoading) {
    return (
      <Container maxWidth="xl" sx={{ py: 3, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress size={60} />
      </Container>
    );
  }

  // Show message if not authenticated (should redirect, but just in case)
  if (!isAuthenticated) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Alert severity="warning">
          Please log in to access your portfolio.
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 700, display: 'flex', alignItems: 'center' }}>
          <BusinessCenter sx={{ mr: 2, color: 'primary.main' }} />
          Portfolio Management
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Comprehensive portfolio tracking, analysis, and risk management in one integrated platform.
        </Typography>
      </Box>

      {/* Portfolio Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Total Value
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main' }}>
                {formatCurrency(portfolioData.totalValue)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Total Gain/Loss
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700, color: getGainLossColor(portfolioData.totalGainLoss) }}>
                {formatCurrency(portfolioData.totalGainLoss)}
              </Typography>
              <Typography variant="body2" sx={{ color: getGainLossColor(portfolioData.totalGainLossPercent) }}>
                {formatPercentage(portfolioData.totalGainLossPercent)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Value at Risk (95%)
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: 'error.main' }}>
                {formatCurrency(portfolioData.riskMetrics.currentVaR)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                1-day potential loss
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Sharpe Ratio
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: 'success.main' }}>
                {portfolioData.riskMetrics.sharpeRatio?.toFixed(2) || 'N/A'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Risk-adjusted return
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
        <Tab label="Holdings" icon={<AccountBalance />} />
        <Tab label="Allocation Analysis" icon={<PieChartIcon />} />
        <Tab label="Risk Overview" icon={<Security />} />
        <Tab label="Alerts & Monitoring" icon={<NotificationsActive />} />
        <Tab label="Stress Testing" icon={<Report />} />
        <Tab label="Risk Limits" icon={<Settings />} />
        <Tab label="Import Portfolio" icon={<Download />} />
      </Tabs>

      <TabPanel value={activeTab} index={0}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6">Current Holdings</Typography>
          <Box>
            <Button
              variant="outlined"
              startIcon={<Download />}
              onClick={exportPortfolio}
              sx={{ mr: 1 }}
            >
              Export
            </Button>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setAddHoldingDialog(true)}
            >
              Add Holding
            </Button>
          </Box>
        </Box>

        <Card>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Company</TableCell>
                  <TableCell align="right">Shares</TableCell>
                  <TableCell align="right">Avg Cost</TableCell>
                  <TableCell align="right">Current Price</TableCell>
                  <TableCell align="right">Market Value</TableCell>
                  <TableCell align="right">Gain/Loss</TableCell>
                  <TableCell align="right">Allocation</TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {portfolioData.holdings
                  .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                  .map((holding) => (
                  <TableRow key={holding.symbol} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {holding.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {holding.company}
                      </Typography>
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
                      {formatCurrency(holding.marketValue)}
                    </TableCell>
                    <TableCell align="right">
                      <Box>
                        <Typography variant="body2" sx={{ color: getGainLossColor(holding.gainLoss) }}>
                          {formatCurrency(holding.gainLoss)}
                        </Typography>
                        <Typography variant="caption" sx={{ color: getGainLossColor(holding.gainLossPercent) }}>
                          {formatPercentage(holding.gainLossPercent)}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <LinearProgress 
                        variant="determinate" 
                        value={holding.allocation} 
                        sx={{ width: 60, mr: 1, display: 'inline-block' }}
                      />
                      {holding.allocation.toFixed(1)}%
                    </TableCell>
                    <TableCell align="center">
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => removeHolding(holding.symbol)}
                      >
                        <Delete />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={portfolioData.holdings.length}
            page={page}
            onPageChange={(e, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value));
              setPage(0);
            }}
          />
        </Card>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Sector Allocation" />
              <CardContent>
                <Box sx={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={portfolioData.sectorAllocation}
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                        label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                      >
                        {portfolioData.sectorAllocation.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <RechartsTooltip formatter={(value) => [`${value.toFixed(1)}%`, 'Allocation']} />
                    </PieChart>
                  </ResponsiveContainer>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Asset Style Allocation" />
              <CardContent>
                <Box sx={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={portfolioData.assetAllocation}
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                        label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                      >
                        {portfolioData.assetAllocation.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <RechartsTooltip formatter={(value) => [`${value.toFixed(1)}%`, 'Allocation']} />
                    </PieChart>
                  </ResponsiveContainer>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Risk Metrics Overview */}
        <Card sx={{ mt: 3 }}>
          <CardHeader title="Portfolio Risk Metrics" />
          <CardContent>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Beta
                </Typography>
                <Typography variant="h6">
                  {portfolioData.riskMetrics.beta?.toFixed(2) || 'N/A'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Market sensitivity
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Volatility
                </Typography>
                <Typography variant="h6" sx={{ color: 'warning.main' }}>
                  {formatPercentage(portfolioData.riskMetrics.volatility)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Annualized
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Max Drawdown
                </Typography>
                <Typography variant="h6" sx={{ color: 'error.main' }}>
                  {formatPercentage(portfolioData.riskMetrics.maxDrawdown)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Historical peak decline
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Sortino Ratio
                </Typography>
                <Typography variant="h6" sx={{ color: 'success.main' }}>
                  {portfolioData.riskMetrics.sortino?.toFixed(2) || 'N/A'}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Downside deviation adjusted
                </Typography>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Risk Profile Overview" />
              <CardContent>
                <Grid container spacing={3}>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Risk Level
                    </Typography>
                    <Chip 
                      label={portfolioData.riskMetrics.riskLevel || 'Moderate'} 
                      color={getRiskColor(portfolioData.riskMetrics.riskLevel)}
                      size="large"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" color="text.secondary" gutterBottom>
                      Expected Shortfall
                    </Typography>
                    <Typography variant="h6" sx={{ color: 'error.main' }}>
                      {formatCurrency(portfolioData.riskMetrics.expectedShortfall)}
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Risk Gauge" />
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 200 }}>
                  <Box sx={{ position: 'relative', display: 'inline-flex' }}>
                    <CircularProgress
                      variant="determinate"
                      value={(portfolioData.riskMetrics.volatility || 0) * 4}
                      size={120}
                      thickness={4}
                      color={getRiskColor(portfolioData.riskMetrics.riskLevel)}
                    />
                    <Box
                      sx={{
                        top: 0,
                        left: 0,
                        bottom: 0,
                        right: 0,
                        position: 'absolute',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexDirection: 'column'
                      }}
                    >
                      <Typography variant="h6" component="div" color="text.secondary">
                        Risk
                      </Typography>
                      <Typography variant="body2" component="div" color="text.secondary">
                        {portfolioData.riskMetrics.riskLevel || 'Moderate'}
                      </Typography>
                    </Box>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Correlation Matrix */}
        <Card sx={{ mt: 3 }}>
          <CardHeader title="Asset Correlation Matrix" />
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Asset</TableCell>
                  <TableCell align="center">Correlation</TableCell>
                  <TableCell align="center">Risk Level</TableCell>
                  <TableCell align="center">Correlation Bar</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {portfolioData.correlationMatrix.map((item) => (
                  <TableRow key={item.asset} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {item.asset}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      {item.correlation.toFixed(2)}
                    </TableCell>
                    <TableCell align="center">
                      <Chip 
                        label={item.risk} 
                        color={getRiskColor(item.risk)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <LinearProgress 
                        variant="determinate" 
                        value={Math.abs(item.correlation) * 100} 
                        sx={{ width: 100 }}
                        color={item.correlation > 0.8 ? 'error' : item.correlation > 0.5 ? 'warning' : 'success'}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6">Risk Alerts</Typography>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAlertDialogOpen(true)}
          >
            Create Alert
          </Button>
        </Box>

        <Grid container spacing={2}>
          {portfolioData.riskAlerts.map((alert) => (
            <Grid item xs={12} key={alert.id}>
              <Alert 
                severity={getSeverityColor(alert.severity)}
                action={
                  alert.active && (
                    <IconButton
                      color="inherit"
                      size="small"
                      onClick={() => dismissAlert(alert.id)}
                    >
                      <Delete />
                    </IconButton>
                  )
                }
                sx={{ opacity: alert.active ? 1 : 0.6 }}
              >
                <Box>
                  <Typography variant="body2" fontWeight="bold">
                    {alert.type}
                  </Typography>
                  <Typography variant="body2">
                    {alert.message}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {new Date(alert.timestamp).toLocaleString()}
                  </Typography>
                </Box>
              </Alert>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={4}>
        <Typography variant="h6" gutterBottom>
          Historical Stress Test Scenarios
        </Typography>
        
        <Grid container spacing={2}>
          {portfolioData.stressTests.map((test, index) => (
            <Grid item xs={12} sm={6} md={6} key={index}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    {test.scenario}
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2" color="text.secondary">
                      Portfolio Impact:
                    </Typography>
                    <Typography variant="body2" sx={{ color: 'error.main', fontWeight: 'bold' }}>
                      {formatPercentage(test.portfolioImpact)}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2" color="text.secondary">
                      Timeframe:
                    </Typography>
                    <Typography variant="body2">
                      {test.timeframe}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">
                      Probability:
                    </Typography>
                    <Chip 
                      label={test.probability} 
                      color={getRiskColor(test.probability)}
                      size="small"
                    />
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={5}>
        <Typography variant="h6" gutterBottom>
          Risk Limit Configuration
        </Typography>
        
        <Grid container spacing={3}>
          {Object.entries(portfolioData.riskLimits).map(([key, value]) => (
            <Grid item xs={12} sm={6} md={4} key={key}>
              <Card>
                <CardContent>
                  <Typography variant="body2" color="text.secondary" gutterBottom sx={{ textTransform: 'capitalize' }}>
                    {key.replace(/([A-Z])/g, ' $1').trim()}
                  </Typography>
                  <Typography variant="h6" sx={{ mb: 2 }}>
                    {typeof value === 'number' ? (key.includes('max') || key.includes('min') ? `${value}%` : value.toFixed(2)) : value}
                  </Typography>
                  <Slider
                    value={value}
                    onChange={(e, newValue) => {
                      setPortfolioData(prev => ({
                        ...prev,
                        riskLimits: { ...prev.riskLimits, [key]: newValue }
                      }));
                    }}
                    min={0}
                    max={key.includes('Beta') ? 2 : 100}
                    step={key.includes('Beta') ? 0.1 : 1}
                    valueLabelDisplay="auto"
                    size="small"
                  />
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={6}>
        <Typography variant="h6" gutterBottom>
          Import Portfolio from Broker
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Connect your brokerage account to automatically import your portfolio. Your API credentials are encrypted and stored securely.
        </Typography>
        
        <Grid container spacing={3}>
          {/* Connect Broker Section */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                  <Security sx={{ mr: 1, color: 'primary.main' }} />
                  Connect Broker
                </Typography>
                
                <Grid container spacing={2} sx={{ mt: 1 }}>
                  <Grid item xs={12}>
                    <FormControl fullWidth>
                      <InputLabel>Broker</InputLabel>
                      <Select value="alpaca" disabled>
                        <MenuItem value="alpaca">Alpaca Markets</MenuItem>
                        <MenuItem value="robinhood">Robinhood (Coming Soon)</MenuItem>
                        <MenuItem value="td_ameritrade">TD Ameritrade (Coming Soon)</MenuItem>
                        <MenuItem value="fidelity">Fidelity (Coming Soon)</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                  
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="API Key"
                      type="password"
                      placeholder="Enter your API key"
                      helperText="Your API key will be encrypted before storage"
                    />
                  </Grid>
                  
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      label="API Secret"
                      type="password"
                      placeholder="Enter your API secret"
                      helperText="Required for some brokers"
                    />
                  </Grid>
                  
                  <Grid item xs={12}>
                    <FormControlLabel
                      control={<Switch defaultChecked />}
                      label="Use Sandbox Mode"
                    />
                  </Grid>
                  
                  <Grid item xs={12}>
                    <Button variant="contained" fullWidth disabled>
                      Connect Broker
                    </Button>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>
          
          {/* Import Status Section */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                  <Download sx={{ mr: 1, color: 'success.main' }} />
                  Import Portfolio
                </Typography>
                
                <Alert severity="info" sx={{ mb: 2 }}>
                  No broker connections found. Connect a broker to import your portfolio automatically.
                </Alert>
                
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <Button variant="outlined" disabled>
                    Import from Alpaca
                  </Button>
                  
                  <Divider sx={{ my: 1 }}>OR</Divider>
                  
                  <Typography variant="body2" color="text.secondary">
                    Manual CSV Import (Coming Soon)
                  </Typography>
                  <Button variant="outlined" disabled>
                    Upload CSV File
                  </Button>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          
          {/* Security Information */}
          <Grid item xs={12}>
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                  <Shield sx={{ mr: 1, color: 'success.main' }} />
                  Security & Privacy
                </Typography>
                
                <Grid container spacing={2}>
                  <Grid item xs={12} md={4}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      <CheckCircle sx={{ color: 'success.main', mr: 1, fontSize: 20 }} />
                      <Typography variant="body2">AES-256 Encryption</Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                      All API credentials are encrypted using industry-standard AES-256-GCM encryption
                    </Typography>
                  </Grid>
                  
                  <Grid item xs={12} md={4}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      <CheckCircle sx={{ color: 'success.main', mr: 1, fontSize: 20 }} />
                      <Typography variant="body2">Zero Logging</Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                      API keys are never logged in plaintext and are stored with user-specific encryption
                    </Typography>
                  </Grid>
                  
                  <Grid item xs={12} md={4}>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                      <CheckCircle sx={{ color: 'success.main', mr: 1, fontSize: 20 }} />
                      <Typography variant="body2">Read-Only Access</Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                      Portfolio import only requires read permissions to view your positions
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Add Holding Dialog */}
      <Dialog open={addHoldingDialog} onClose={() => setAddHoldingDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add New Holding</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                label="Symbol"
                fullWidth
                value={newHolding.symbol}
                onChange={(e) => setNewHolding(prev => ({ ...prev, symbol: e.target.value.toUpperCase() }))}
                placeholder="e.g., AAPL"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="Shares"
                type="number"
                fullWidth
                value={newHolding.shares}
                onChange={(e) => setNewHolding(prev => ({ ...prev, shares: e.target.value }))}
                placeholder="100"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="Average Cost"
                type="number"
                fullWidth
                value={newHolding.avgCost}
                onChange={(e) => setNewHolding(prev => ({ ...prev, avgCost: e.target.value }))}
                placeholder="150.00"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                label="Current Price (optional)"
                type="number"
                fullWidth
                value={newHolding.currentPrice}
                onChange={(e) => setNewHolding(prev => ({ ...prev, currentPrice: e.target.value }))}
                placeholder="175.43"
                helperText="Leave blank to use average cost"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddHoldingDialog(false)}>Cancel</Button>
          <Button onClick={addHolding} variant="contained">Add Holding</Button>
        </DialogActions>
      </Dialog>

      {/* Create Alert Dialog */}
      <Dialog open={alertDialogOpen} onClose={() => setAlertDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Risk Alert</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Alert Type</InputLabel>
                <Select
                  value={newAlert.type}
                  onChange={(e) => setNewAlert(prev => ({ ...prev, type: e.target.value }))}
                >
                  <MenuItem value="portfolio_loss">Portfolio Loss</MenuItem>
                  <MenuItem value="volatility">High Volatility</MenuItem>
                  <MenuItem value="beta">Beta Alert</MenuItem>
                  <MenuItem value="sector_concentration">Sector Concentration</MenuItem>
                  <MenuItem value="position_size">Position Size</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Condition</InputLabel>
                <Select
                  value={newAlert.condition}
                  onChange={(e) => setNewAlert(prev => ({ ...prev, condition: e.target.value }))}
                >
                  <MenuItem value="greater_than">Greater Than</MenuItem>
                  <MenuItem value="less_than">Less Than</MenuItem>
                  <MenuItem value="equals">Equals</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                label="Threshold (%)"
                type="number"
                fullWidth
                value={newAlert.threshold}
                onChange={(e) => setNewAlert(prev => ({ ...prev, threshold: e.target.value }))}
                placeholder="10"
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={newAlert.enabled}
                    onChange={(e) => setNewAlert(prev => ({ ...prev, enabled: e.target.checked }))}
                  />
                }
                label="Enable Alert"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAlertDialogOpen(false)}>Cancel</Button>
          <Button onClick={createAlert} variant="contained">Create Alert</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default Portfolio;