import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Divider,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
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
  Alert,
  Tooltip,
  Fab,
  Menu,
  MenuItem,
  Switch,
  FormControlLabel,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Stack,
  Avatar,
  AvatarGroup
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  TrendingUp,
  TrendingDown,
  AttachMoney,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon,
  Timeline,
  Sync as SyncIcon,
  Settings as SettingsIcon,
  Upload as UploadIcon,
  Download as DownloadIcon,
  Refresh as RefreshIcon,
  ExpandMore,
  AccountBalance,
  Business,
  ShowChart,
  Analytics,
  Info,
  Warning,
  CheckCircle,
  Error,
  Key as KeyIcon,
  CloudUpload,
  ManualRecord
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, ComposedChart, Area, AreaChart } from 'recharts';
import { formatCurrency, formatNumber, formatPercentage } from '../utils/formatters';
import { format } from 'date-fns';

const COLORS = ['#1976d2', '#43a047', '#ffb300', '#8e24aa', '#e53935', '#00bcd4', '#ff7043', '#9e9e9e'];

// Sample portfolio data (will be replaced with real data)
const samplePortfolioData = {
  totalValue: 1247850.32,
  dayChange: 15420.15,
  dayChangePercent: 1.25,
  totalReturn: 187654.32,
  totalReturnPercent: 17.7,
  cash: 25000.00,
  marginUsed: 0,
  buyingPower: 25000.00,
  positions: [
    {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      shares: 150,
      avgPrice: 175.50,
      currentPrice: 182.25,
      marketValue: 27337.50,
      dayChange: 1.15,
      dayChangePercent: 0.63,
      totalReturn: 1012.50,
      totalReturnPercent: 3.84,
      sector: 'Technology',
      allocation: 2.2
    },
    {
      symbol: 'MSFT',
      name: 'Microsoft Corporation',
      shares: 100,
      avgPrice: 385.20,
      currentPrice: 412.78,
      marketValue: 41278.00,
      dayChange: -2.15,
      dayChangePercent: -0.52,
      totalReturn: 2758.00,
      totalReturnPercent: 7.16,
      sector: 'Technology',
      allocation: 3.3
    },
    {
      symbol: 'NVDA',
      name: 'NVIDIA Corporation',
      shares: 75,
      avgPrice: 721.80,
      currentPrice: 845.32,
      marketValue: 63399.00,
      dayChange: 12.45,
      dayChangePercent: 1.49,
      totalReturn: 9264.00,
      totalReturnPercent: 17.1,
      sector: 'Technology',
      allocation: 5.1
    },
    {
      symbol: 'SPY',
      name: 'SPDR S&P 500 ETF Trust',
      shares: 500,
      avgPrice: 428.15,
      currentPrice: 448.75,
      marketValue: 224375.00,
      dayChange: 1.25,
      dayChangePercent: 0.28,
      totalReturn: 10300.00,
      totalReturnPercent: 4.81,
      sector: 'ETF',
      allocation: 18.0
    },
    {
      symbol: 'GOOGL',
      name: 'Alphabet Inc.',
      shares: 85,
      avgPrice: 142.30,
      currentPrice: 156.78,
      marketValue: 13326.30,
      dayChange: 0.85,
      dayChangePercent: 0.55,
      totalReturn: 1230.80,
      totalReturnPercent: 10.2,
      sector: 'Technology',
      allocation: 1.1
    }
  ],
  performance: [
    { date: '2024-06-01', value: 1180000, benchmark: 1170000 },
    { date: '2024-06-15', value: 1195000, benchmark: 1175000 },
    { date: '2024-07-01', value: 1247850, benchmark: 1190000 }
  ],
  allocation: {
    bySector: [
      { name: 'Technology', value: 65.2, amount: 813450 },
      { name: 'ETF', value: 18.0, amount: 224375 },
      { name: 'Healthcare', value: 8.5, amount: 106068 },
      { name: 'Financials', value: 5.8, amount: 72375 },
      { name: 'Cash', value: 2.5, amount: 31582 }
    ],
    byAssetType: [
      { name: 'Individual Stocks', value: 75.2 },
      { name: 'ETFs', value: 22.3 },
      { name: 'Cash', value: 2.5 }
    ]
  }
};

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
        <Box sx={{ pt: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

function Portfolio() {
  const [tabValue, setTabValue] = useState(0);
  const [portfolioData, setPortfolioData] = useState(samplePortfolioData);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showApiDialog, setShowApiDialog] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [isApiConnected, setIsApiConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [newPosition, setNewPosition] = useState({
    symbol: '',
    shares: '',
    avgPrice: '',
    currentPrice: ''
  });

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const handleAddPosition = () => {
    if (newPosition.symbol && newPosition.shares && newPosition.avgPrice) {
      const shares = parseFloat(newPosition.shares);
      const avgPrice = parseFloat(newPosition.avgPrice);
      const currentPrice = parseFloat(newPosition.currentPrice) || avgPrice;
      const marketValue = shares * currentPrice;
      const totalReturn = (currentPrice - avgPrice) * shares;
      const totalReturnPercent = ((currentPrice - avgPrice) / avgPrice) * 100;

      const position = {
        symbol: newPosition.symbol.toUpperCase(),
        name: `${newPosition.symbol.toUpperCase()} Inc.`,
        shares,
        avgPrice,
        currentPrice,
        marketValue,
        dayChange: 0,
        dayChangePercent: 0,
        totalReturn,
        totalReturnPercent,
        sector: 'Unknown',
        allocation: (marketValue / portfolioData.totalValue) * 100
      };

      setPortfolioData(prev => ({
        ...prev,
        positions: [...prev.positions, position],
        totalValue: prev.totalValue + marketValue
      }));

      setNewPosition({ symbol: '', shares: '', avgPrice: '', currentPrice: '' });
      setShowAddDialog(false);
    }
  };

  const handleConnectAlpaca = async () => {
    if (!apiKey) return;
    
    setLoading(true);
    // Simulate API connection
    setTimeout(() => {
      setIsApiConnected(true);
      setLoading(false);
      setShowApiDialog(false);
      // Here you would implement actual Alpaca API integration
    }, 2000);
  };

  const handleRefreshData = () => {
    setLoading(true);
    // Simulate data refresh
    setTimeout(() => {
      setLoading(false);
    }, 1500);
  };

  const getSectorColor = (sector) => {
    const sectorColors = {
      'Technology': '#1976d2',
      'ETF': '#43a047',
      'Healthcare': '#ff9800',
      'Financials': '#9c27b0',
      'Cash': '#607d8b'
    };
    return sectorColors[sector] || '#9e9e9e';
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
            Portfolio
          </Typography>
          <Typography variant="subtitle1" color="textSecondary">
            Total Value: {formatCurrency(portfolioData.totalValue)} • 
            {portfolioData.dayChange >= 0 ? '+' : ''}{formatCurrency(portfolioData.dayChange)} 
            ({portfolioData.dayChangePercent >= 0 ? '+' : ''}{portfolioData.dayChangePercent.toFixed(2)}%) today
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant="outlined"
            startIcon={<KeyIcon />}
            onClick={() => setShowApiDialog(true)}
            color={isApiConnected ? 'success' : 'primary'}
          >
            {isApiConnected ? 'Connected' : 'Connect Alpaca'}
          </Button>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setShowAddDialog(true)}
          >
            Add Position
          </Button>
          <IconButton onClick={handleRefreshData} disabled={loading}>
            <RefreshIcon />
          </IconButton>
        </Box>
      </Box>

      {/* Connection Status */}
      {isApiConnected && (
        <Alert severity="success" sx={{ mb: 3 }}>
          <Box display="flex" alignItems="center" gap={1}>
            <CheckCircle fontSize="small" />
            <Typography variant="body2">
              Connected to Alpaca Markets API • Live data sync enabled
            </Typography>
          </Box>
        </Alert>
      )}

      {/* Portfolio Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={1}>
                <AttachMoney color="primary" />
                <Typography variant="h6" fontWeight={600}>Total Value</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color="primary">
                {formatCurrency(portfolioData.totalValue)}
              </Typography>
              <Chip
                icon={portfolioData.dayChange >= 0 ? <TrendingUp /> : <TrendingDown />}
                label={`${portfolioData.dayChange >= 0 ? '+' : ''}${formatCurrency(portfolioData.dayChange)} (${portfolioData.dayChangePercent >= 0 ? '+' : ''}${portfolioData.dayChangePercent.toFixed(2)}%)`}
                color={portfolioData.dayChange >= 0 ? 'success' : 'error'}
                size="small"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={1}>
                <Timeline color="primary" />
                <Typography variant="h6" fontWeight={600}>Total Return</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color={portfolioData.totalReturn >= 0 ? 'success.main' : 'error.main'}>
                {formatCurrency(portfolioData.totalReturn)}
              </Typography>
              <Typography variant="body2" color="textSecondary" mt={1}>
                {portfolioData.totalReturnPercent >= 0 ? '+' : ''}{portfolioData.totalReturnPercent.toFixed(2)}% overall
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={1}>
                <AccountBalance color="primary" />
                <Typography variant="h6" fontWeight={600}>Cash Available</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold">
                {formatCurrency(portfolioData.cash)}
              </Typography>
              <Typography variant="body2" color="textSecondary" mt={1}>
                Buying Power: {formatCurrency(portfolioData.buyingPower)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={1}>
                <PieChartIcon color="primary" />
                <Typography variant="h6" fontWeight={600}>Positions</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold">
                {portfolioData.positions.length}
              </Typography>
              <Typography variant="body2" color="textSecondary" mt={1}>
                Diversified portfolio
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="Holdings" />
          <Tab label="Performance" />
          <Tab label="Allocation" />
          <Tab label="Analysis" />
        </Tabs>
      </Box>

      {/* Holdings Tab */}
      <TabPanel value={tabValue} index={0}>
        <Card elevation={2}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Current Holdings
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Company</TableCell>
                    <TableCell align="right">Shares</TableCell>
                    <TableCell align="right">Avg Price</TableCell>
                    <TableCell align="right">Current Price</TableCell>
                    <TableCell align="right">Market Value</TableCell>
                    <TableCell align="right">Day Change</TableCell>
                    <TableCell align="right">Total Return</TableCell>
                    <TableCell align="right">Allocation</TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {portfolioData.positions.map((position, index) => (
                    <TableRow key={position.symbol} hover>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          <Avatar sx={{ width: 32, height: 32, backgroundColor: getSectorColor(position.sector) }}>
                            {position.symbol.charAt(0)}
                          </Avatar>
                          <Typography variant="body2" fontWeight={600}>
                            {position.symbol}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{position.name}</Typography>
                        <Typography variant="caption" color="textSecondary">{position.sector}</Typography>
                      </TableCell>
                      <TableCell align="right">{formatNumber(position.shares)}</TableCell>
                      <TableCell align="right">{formatCurrency(position.avgPrice)}</TableCell>
                      <TableCell align="right">{formatCurrency(position.currentPrice)}</TableCell>
                      <TableCell align="right">{formatCurrency(position.marketValue)}</TableCell>
                      <TableCell align="right">
                        <Chip
                          icon={position.dayChange >= 0 ? <TrendingUp /> : <TrendingDown />}
                          label={`${position.dayChange >= 0 ? '+' : ''}${position.dayChangePercent.toFixed(2)}%`}
                          color={position.dayChange >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Box>
                          <Typography variant="body2" color={position.totalReturn >= 0 ? 'success.main' : 'error.main'} fontWeight={600}>
                            {formatCurrency(position.totalReturn)}
                          </Typography>
                          <Typography variant="caption" color={position.totalReturn >= 0 ? 'success.main' : 'error.main'}>
                            {position.totalReturnPercent >= 0 ? '+' : ''}{position.totalReturnPercent.toFixed(2)}%
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2" fontWeight={600}>
                          {position.allocation.toFixed(1)}%
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        <IconButton size="small">
                          <EditIcon />
                        </IconButton>
                        <IconButton size="small" color="error">
                          <DeleteIcon />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </TabPanel>

      {/* Performance Tab */}
      <TabPanel value={tabValue} index={1}>
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Portfolio Performance vs S&P 500
                </Typography>
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={portfolioData.performance}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => [formatCurrency(value), '']} />
                    <Area type="monotone" dataKey="value" stackId="1" stroke="#1976d2" fill="#1976d2" fillOpacity={0.3} name="Portfolio" />
                    <Area type="monotone" dataKey="benchmark" stackId="2" stroke="#ff7043" fill="#ff7043" fillOpacity={0.3} name="S&P 500" />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Allocation Tab */}
      <TabPanel value={tabValue} index={2}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Allocation by Sector
                </Typography>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={portfolioData.allocation.bySector}
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      fill="#8884d8"
                      dataKey="value"
                      label={({ name, value }) => `${name}: ${value}%`}
                    >
                      {portfolioData.allocation.bySector.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip formatter={(value) => [`${value}%`, '']} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Asset Type Breakdown
                </Typography>
                <Box sx={{ mt: 2 }}>
                  {portfolioData.allocation.byAssetType.map((asset, index) => (
                    <Box key={asset.name} sx={{ mb: 2 }}>
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                        <Typography variant="body2">{asset.name}</Typography>
                        <Typography variant="body2" fontWeight={600}>{asset.value}%</Typography>
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={asset.value}
                        sx={{
                          height: 8,
                          borderRadius: 4,
                          backgroundColor: 'grey.200',
                          '& .MuiLinearProgress-bar': {
                            backgroundColor: COLORS[index % COLORS.length]
                          }
                        }}
                      />
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Analysis Tab */}
      <TabPanel value={tabValue} index={3}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Risk Metrics
                </Typography>
                <Box>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="textSecondary">Portfolio Beta</Typography>
                    <Typography variant="h6" fontWeight={600}>0.92</Typography>
                    <Typography variant="caption" color="textSecondary">Lower volatility than market</Typography>
                  </Box>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="textSecondary">Sharpe Ratio</Typography>
                    <Typography variant="h6" fontWeight={600}>1.85</Typography>
                    <Typography variant="caption" color="textSecondary">Excellent risk-adjusted returns</Typography>
                  </Box>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="textSecondary">Max Drawdown</Typography>
                    <Typography variant="h6" fontWeight={600}>-8.2%</Typography>
                    <Typography variant="caption" color="textSecondary">Well controlled downside</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">Volatility (Annualized)</Typography>
                    <Typography variant="h6" fontWeight={600}>15.4%</Typography>
                    <Typography variant="caption" color="textSecondary">Moderate risk profile</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Portfolio Health Score
                </Typography>
                <Box textAlign="center" py={2}>
                  <Typography variant="h2" fontWeight="bold" color="success.main">
                    A+
                  </Typography>
                  <Typography variant="body1" color="textSecondary" mt={1}>
                    Excellent portfolio performance
                  </Typography>
                  <Box sx={{ mt: 3 }}>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Diversification</Typography>
                      <Typography variant="body2" fontWeight={600}>95%</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Risk Management</Typography>
                      <Typography variant="body2" fontWeight={600}>88%</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Performance</Typography>
                      <Typography variant="body2" fontWeight={600}>92%</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2">Cost Efficiency</Typography>
                      <Typography variant="body2" fontWeight={600}>96%</Typography>
                    </Box>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Add Position Dialog */}
      <Dialog open={showAddDialog} onClose={() => setShowAddDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add New Position</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <TextField
              fullWidth
              label="Symbol"
              value={newPosition.symbol}
              onChange={(e) => setNewPosition({ ...newPosition, symbol: e.target.value })}
              sx={{ mb: 2 }}
              placeholder="AAPL"
            />
            <TextField
              fullWidth
              label="Number of Shares"
              type="number"
              value={newPosition.shares}
              onChange={(e) => setNewPosition({ ...newPosition, shares: e.target.value })}
              sx={{ mb: 2 }}
            />
            <TextField
              fullWidth
              label="Average Price"
              type="number"
              value={newPosition.avgPrice}
              onChange={(e) => setNewPosition({ ...newPosition, avgPrice: e.target.value })}
              sx={{ mb: 2 }}
              placeholder="150.00"
            />
            <TextField
              fullWidth
              label="Current Price (optional)"
              type="number"
              value={newPosition.currentPrice}
              onChange={(e) => setNewPosition({ ...newPosition, currentPrice: e.target.value })}
              placeholder="Will use average price if not provided"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowAddDialog(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleAddPosition}>Add Position</Button>
        </DialogActions>
      </Dialog>

      {/* Alpaca API Dialog */}
      <Dialog open={showApiDialog} onClose={() => setShowApiDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Connect to Alpaca Markets</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="textSecondary" paragraph>
            Connect your Alpaca Markets account to automatically sync your portfolio data.
          </Typography>
          <TextField
            fullWidth
            label="Alpaca API Key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            sx={{ mb: 2 }}
            placeholder="Enter your Alpaca API key"
          />
          <Alert severity="info">
            Your API key is stored securely and only used to fetch portfolio data. We never store or transmit sensitive information.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowApiDialog(false)}>Cancel</Button>
          <Button 
            variant="contained" 
            onClick={handleConnectAlpaca}
            disabled={!apiKey || loading}
          >
            {loading ? 'Connecting...' : 'Connect'}
          </Button>
        </DialogActions>
      </Dialog>

      {loading && <LinearProgress />}
    </Box>
  );
}

export default Portfolio;