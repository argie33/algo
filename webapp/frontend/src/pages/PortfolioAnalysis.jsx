import React, { useState, useEffect } from 'react';
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
  Divider
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
  AreaChart
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
  Download
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

const PortfolioAnalysis = () => {
  const { apiUrl: API_BASE } = getApiConfig();
  
  const [activeTab, setActiveTab] = useState(0);
  const [portfolioData, setPortfolioData] = useState({
    holdings: [],
    totalValue: 0,
    totalGainLoss: 0,
    totalGainLossPercent: 0,
    assetAllocation: [],
    sectorAllocation: [],
    riskMetrics: {}
  });
  const [loading, setLoading] = useState(false);
  const [addHoldingDialog, setAddHoldingDialog] = useState(false);
  const [newHolding, setNewHolding] = useState({
    symbol: '',
    shares: '',
    avgCost: '',
    currentPrice: ''
  });

  // Mock portfolio data for demonstration
  const mockPortfolio = {
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
      beta: 1.15,
      sharpeRatio: 0.87,
      volatility: 18.5,
      maxDrawdown: -12.3,
      correlation: 0.92
    }
  };

  useEffect(() => {
    loadPortfolioData();
  }, []);

  const loadPortfolioData = async () => {
    setLoading(true);
    try {
      // Try to fetch from API, fallback to mock data
      const response = await fetch(`${API_BASE}/api/portfolio/analysis`);
      if (response.ok) {
        const data = await response.json();
        setPortfolioData(data);
      } else {
        setPortfolioData(mockPortfolio);
      }
    } catch (error) {
      console.error('Failed to load portfolio data:', error);
      setPortfolioData(mockPortfolio);
    } finally {
      setLoading(false);
    }
  };

  const addHolding = async () => {
    if (!newHolding.symbol || !newHolding.shares || !newHolding.avgCost) return;

    try {
      // Calculate derived values
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
        allocation: 0 // Will be recalculated
      };

      // Add to holdings and recalculate portfolio
      const newHoldings = [...portfolioData.holdings, holding];
      const newTotalValue = newHoldings.reduce((sum, h) => sum + h.marketValue, 0);
      
      // Update allocations
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
    
    // Update allocations
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
    a.download = 'portfolio_analysis.csv';
    a.click();
  };

  const getGainLossColor = (value) => {
    if (value > 0) return 'success.main';
    if (value < 0) return 'error.main';
    return 'text.secondary';
  };

  const getRiskColor = (metric, value) => {
    switch (metric) {
      case 'beta':
        if (value > 1.2) return 'error';
        if (value < 0.8) return 'info';
        return 'warning';
      case 'sharpeRatio':
        if (value > 1) return 'success';
        if (value < 0.5) return 'error';
        return 'warning';
      case 'volatility':
        if (value > 25) return 'error';
        if (value < 15) return 'success';
        return 'warning';
      default:
        return 'primary';
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 700, display: 'flex', alignItems: 'center' }}>
          <Analytics sx={{ mr: 2, color: 'primary.main' }} />
          Portfolio Analysis
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Comprehensive analysis of your investment portfolio including performance, allocation, and risk metrics.
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
                Holdings
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>
                {portfolioData.holdings.length}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Active positions
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Beta
              </Typography>
              <Typography variant="h4" sx={{ fontWeight: 700 }}>
                {portfolioData.riskMetrics.beta?.toFixed(2) || 'N/A'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                vs Market
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
        <Tab label="Holdings" icon={<AccountBalance />} />
        <Tab label="Allocation" icon={<PieChartIcon />} />
        <Tab label="Performance" icon={<ShowChart />} />
        <Tab label="Risk Analysis" icon={<Assessment />} />
      </Tabs>

      <TabPanel value={activeTab} index={0}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6">Current Holdings</Typography>
          <Box>
            <Button
              variant="outlined"
              startIcon={<Upload />}
              sx={{ mr: 1 }}
              disabled
            >
              Import
            </Button>
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
                {portfolioData.holdings.map((holding) => (
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
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Alert severity="info" sx={{ mb: 2 }}>
          Performance tracking coming soon. Connect your brokerage account to see historical performance data.
        </Alert>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        <Typography variant="h6" gutterBottom>
          Risk Metrics
        </Typography>
        
        <Grid container spacing={3}>
          {Object.entries(portfolioData.riskMetrics).map(([metric, value]) => (
            <Grid item xs={12} sm={6} md={4} key={metric}>
              <Card>
                <CardContent>
                  <Typography variant="h6" color="text.secondary" gutterBottom sx={{ textTransform: 'capitalize' }}>
                    {metric.replace(/([A-Z])/g, ' $1').trim()}
                  </Typography>
                  <Chip
                    label={typeof value === 'number' ? value.toFixed(2) : 'N/A'}
                    color={getRiskColor(metric, value)}
                    size="large"
                  />
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    {metric === 'beta' && 'Market sensitivity'}
                    {metric === 'sharpeRatio' && 'Risk-adjusted return'}
                    {metric === 'volatility' && 'Price volatility (%)'}
                    {metric === 'maxDrawdown' && 'Maximum decline (%)'}
                    {metric === 'correlation' && 'Market correlation'}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
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
    </Container>
  );
};

export default PortfolioAnalysis;