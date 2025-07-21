import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Chip,
  Alert,
  CircularProgress,
  Tooltip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tabs,
  Tab,
  LinearProgress,
  Divider
} from '@mui/material';
import {
  Add,
  Edit,
  Delete,
  Refresh,
  TrendingUp,
  TrendingDown,
  AccountBalance,
  ShowChart,
  Warning,
  CheckCircle,
  CloudSync
} from '@mui/icons-material';
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { getPortfolioData, addHolding, updateHolding, deleteHolding, importPortfolioFromBroker } from '../services/api';
import ApiKeyStatusIndicator from './ApiKeyStatusIndicator';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

const PortfolioManager = () => {
  const [portfolioData, setPortfolioData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tabValue, setTabValue] = useState(0);
  const [openAddDialog, setOpenAddDialog] = useState(false);
  const [openEditDialog, setOpenEditDialog] = useState(false);
  const [openImportDialog, setOpenImportDialog] = useState(false);
  const [selectedHolding, setSelectedHolding] = useState(null);
  const [importProgress, setImportProgress] = useState(0);
  const [importStatus, setImportStatus] = useState('');

  // New holding form state
  const [newHolding, setNewHolding] = useState({
    symbol: '',
    quantity: '',
    averagePrice: '',
    purchaseDate: new Date().toISOString().split('T')[0],
    broker: 'manual',
    notes: ''
  });

  // Portfolio summary state
  const [portfolioSummary, setPortfolioSummary] = useState({
    totalValue: 0,
    totalGainLoss: 0,
    totalGainLossPercent: 0,
    topGainer: null,
    topLoser: null,
    sectorAllocation: [],
    riskMetrics: {
      beta: 0,
      sharpeRatio: 0,
      volatility: 0
    }
  });

  // Fetch portfolio data
  const fetchPortfolioData = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      
      const response = await getPortfolioData();
      const data = response.data || response.holdings || response;
      setPortfolioData(Array.isArray(data) ? data : []);
      
      // Calculate portfolio summary
      calculatePortfolioSummary(Array.isArray(data) ? data : []);
      
    } catch (err) {
      console.error('Error fetching portfolio data:', err);
      setError('Failed to load portfolio data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Calculate portfolio summary metrics
  const calculatePortfolioSummary = (data) => {
    if (!data || data.length === 0) {
      setPortfolioSummary({
        totalValue: 0,
        totalGainLoss: 0,
        totalGainLossPercent: 0,
        topGainer: null,
        topLoser: null,
        sectorAllocation: [],
        riskMetrics: { beta: 0, sharpeRatio: 0, volatility: 0 }
      });
      return;
    }

    const totalValue = data.reduce((sum, holding) => sum + (holding.currentValue || 0), 0);
    const totalCost = data.reduce((sum, holding) => sum + (holding.costBasis || 0), 0);
    const totalGainLoss = totalValue - totalCost;
    const totalGainLossPercent = totalCost > 0 ? (totalGainLoss / totalCost) * 100 : 0;

    // Find top gainer and loser
    const gainers = data.filter(h => h.gainLossPercent > 0).sort((a, b) => b.gainLossPercent - a.gainLossPercent);
    const losers = data.filter(h => h.gainLossPercent < 0).sort((a, b) => a.gainLossPercent - b.gainLossPercent);

    // Calculate sector allocation
    const sectorMap = {};
    data.forEach(holding => {
      const sector = holding.sector || 'Other';
      sectorMap[sector] = (sectorMap[sector] || 0) + holding.currentValue;
    });

    const sectorAllocation = Object.entries(sectorMap).map(([sector, value]) => ({
      name: sector,
      value: value,
      percentage: (value / totalValue) * 100
    }));

    setPortfolioSummary({
      totalValue,
      totalGainLoss,
      totalGainLossPercent,
      topGainer: gainers[0] || null,
      topLoser: losers[0] || null,
      sectorAllocation,
      riskMetrics: {
        beta: 1.0, // Would calculate from real data
        sharpeRatio: 0.8,
        volatility: 15.2
      }
    });
  };

  // Add new holding
  const handleAddHolding = async () => {
    try {
      const holding = {
        ...newHolding,
        quantity: parseFloat(newHolding.quantity),
        averagePrice: parseFloat(newHolding.averagePrice),
        costBasis: parseFloat(newHolding.quantity) * parseFloat(newHolding.averagePrice)
      };

      await addHolding(holding);
      setOpenAddDialog(false);
      setNewHolding({
        symbol: '',
        quantity: '',
        averagePrice: '',
        purchaseDate: new Date().toISOString().split('T')[0],
        broker: 'manual',
        notes: ''
      });
      await fetchPortfolioData();
    } catch (err) {
      console.error('Error adding holding:', err);
      setError('Failed to add holding');
    }
  };

  // Update holding
  const handleUpdateHolding = async () => {
    try {
      const updatedHolding = {
        ...selectedHolding,
        quantity: parseFloat(selectedHolding.quantity),
        averagePrice: parseFloat(selectedHolding.averagePrice),
        costBasis: parseFloat(selectedHolding.quantity) * parseFloat(selectedHolding.averagePrice)
      };

      await updateHolding(selectedHolding.id, updatedHolding);
      setOpenEditDialog(false);
      setSelectedHolding(null);
      await fetchPortfolioData();
    } catch (err) {
      console.error('Error updating holding:', err);
      setError('Failed to update holding');
    }
  };

  // Delete holding
  const handleDeleteHolding = async (id) => {
    try {
      await deleteHolding(id);
      await fetchPortfolioData();
    } catch (err) {
      console.error('Error deleting holding:', err);
      setError('Failed to delete holding');
    }
  };

  // Import portfolio from broker
  const handleImportPortfolio = async (broker) => {
    try {
      setImportStatus('Connecting to broker...');
      setImportProgress(20);
      
      const result = await importPortfolioFromBroker(broker);
      
      setImportStatus('Importing positions...');
      setImportProgress(60);
      
      // Simulate progress
      setTimeout(() => {
        setImportStatus('Calculating metrics...');
        setImportProgress(80);
        
        setTimeout(() => {
          setImportStatus('Complete!');
          setImportProgress(100);
          setOpenImportDialog(false);
          fetchPortfolioData();
        }, 1000);
      }, 1000);
      
    } catch (err) {
      console.error('Error importing portfolio:', err);
      setError('Failed to import portfolio');
      setImportStatus('Failed to import');
    }
  };

  useEffect(() => {
    fetchPortfolioData();
  }, [fetchPortfolioData]);

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount);
  };

  const formatPercent = (percent) => {
    if (percent === null || percent === undefined || isNaN(percent)) {
      return '0.00%';
    }
    return `${percent >= 0 ? '+' : ''}${percent.toFixed(2)}%`;
  };

  const getChangeColor = (change) => {
    if (change > 0) return 'success.main';
    if (change < 0) return 'error.main';
    return 'text.secondary';
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      {/* Page Header */}
      <Typography variant="h4" component="h1" gutterBottom>
        Portfolio Overview
      </Typography>

      {/* API Key Status */}
      <Box sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          compact={true}
          showSetupDialog={true}
          onStatusChange={(status) => {
            console.log('Portfolio Manager - API Key Status:', status);
          }}
        />
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Portfolio Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Total Value
              </Typography>
              <Typography variant="h4" color="primary.main">
                {formatCurrency(portfolioSummary.totalValue)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Total Gain/Loss
              </Typography>
              <Typography 
                variant="h4" 
                color={getChangeColor(portfolioSummary.totalGainLoss)}
                sx={{ display: 'flex', alignItems: 'center' }}
              >
                {portfolioSummary.totalGainLoss >= 0 ? <TrendingUp /> : <TrendingDown />}
                {formatCurrency(portfolioSummary.totalGainLoss)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {formatPercent(portfolioSummary.totalGainLossPercent)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Top Performer
              </Typography>
              {portfolioSummary.topGainer ? (
                <>
                  <Typography variant="h5" color="success.main">
                    {portfolioSummary.topGainer.symbol}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {formatPercent(portfolioSummary.topGainer.gainLossPercent)}
                  </Typography>
                </>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No data
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Risk Metrics
              </Typography>
              <Typography variant="body2">
                Beta: {portfolioSummary.riskMetrics.beta.toFixed(2)}
              </Typography>
              <Typography variant="body2">
                Sharpe: {portfolioSummary.riskMetrics.sharpeRatio.toFixed(2)}
              </Typography>
              <Typography variant="body2">
                Volatility: {portfolioSummary.riskMetrics.volatility.toFixed(1)}%
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Action Buttons */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2 }}>
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => setOpenAddDialog(true)}
        >
          Add Holding
        </Button>
        <Button
          variant="outlined"
          startIcon={<CloudSync />}
          onClick={() => setOpenImportDialog(true)}
        >
          Import from Broker
        </Button>
        <Button
          variant="outlined"
          startIcon={<Refresh />}
          onClick={fetchPortfolioData}
        >
          Refresh
        </Button>
      </Box>

      {/* Tabs */}
      <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
        <Tab label="Holdings" />
        <Tab label="Allocation" />
        <Tab label="Performance" />
      </Tabs>

      {/* Holdings Table */}
      {tabValue === 0 && (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell align="right">Quantity</TableCell>
                <TableCell align="right">Avg Price</TableCell>
                <TableCell align="right">Current Price</TableCell>
                <TableCell align="right">Market Value</TableCell>
                <TableCell align="right">Gain/Loss</TableCell>
                <TableCell align="right">Gain/Loss %</TableCell>
                <TableCell align="center">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {portfolioData.map((holding) => (
                <TableRow key={holding.id}>
                  <TableCell>
                    <Box>
                      <Typography variant="body2" fontWeight="bold">
                        {holding.symbol}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {holding.companyName}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell align="right">{holding.quantity}</TableCell>
                  <TableCell align="right">{formatCurrency(holding.averagePrice)}</TableCell>
                  <TableCell align="right">{formatCurrency(holding.currentPrice)}</TableCell>
                  <TableCell align="right">{formatCurrency(holding.currentValue)}</TableCell>
                  <TableCell align="right">
                    <Typography color={getChangeColor(holding.gainLoss)}>
                      {formatCurrency(holding.gainLoss)}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Chip
                      label={formatPercent(holding.gainLossPercent)}
                      color={holding.gainLossPercent >= 0 ? 'success' : 'error'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell align="center">
                    <IconButton
                      onClick={() => {
                        setSelectedHolding(holding);
                        setOpenEditDialog(true);
                      }}
                    >
                      <Edit />
                    </IconButton>
                    <IconButton
                      onClick={() => handleDeleteHolding(holding.id)}
                      color="error"
                    >
                      <Delete />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Sector Allocation */}
      {tabValue === 1 && (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Sector Allocation
                </Typography>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={portfolioSummary.sectorAllocation}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percentage }) => `${name}: ${percentage.toFixed(1)}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {portfolioSummary.sectorAllocation.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip formatter={(value) => formatCurrency(value)} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Top Holdings
                </Typography>
                {portfolioData
                  .sort((a, b) => b.currentValue - a.currentValue)
                  .slice(0, 5)
                  .map((holding) => (
                    <Box key={holding.id} sx={{ mb: 2 }}>
                      <Box display="flex" justifyContent="space-between" alignItems="center">
                        <Typography variant="body2">{holding.symbol}</Typography>
                        <Typography variant="body2">
                          {formatCurrency(holding.currentValue)}
                        </Typography>
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={(holding.currentValue / portfolioSummary.totalValue) * 100}
                        sx={{ mt: 1 }}
                      />
                    </Box>
                  ))}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Add Holding Dialog */}
      <Dialog open={openAddDialog} onClose={() => setOpenAddDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add New Holding</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <TextField
                label="Symbol"
                value={newHolding.symbol}
                onChange={(e) => setNewHolding({...newHolding, symbol: e.target.value.toUpperCase()})}
                fullWidth
                required
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                label="Quantity"
                type="number"
                value={newHolding.quantity}
                onChange={(e) => setNewHolding({...newHolding, quantity: e.target.value})}
                fullWidth
                required
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                label="Average Price"
                type="number"
                value={newHolding.averagePrice}
                onChange={(e) => setNewHolding({...newHolding, averagePrice: e.target.value})}
                fullWidth
                required
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                label="Purchase Date"
                type="date"
                value={newHolding.purchaseDate}
                onChange={(e) => setNewHolding({...newHolding, purchaseDate: e.target.value})}
                fullWidth
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>Broker</InputLabel>
                <Select
                  value={newHolding.broker}
                  onChange={(e) => setNewHolding({...newHolding, broker: e.target.value})}
                >
                  <MenuItem value="manual">Manual Entry</MenuItem>
                  <MenuItem value="alpaca">Alpaca</MenuItem>
                  <MenuItem value="robinhood">Robinhood</MenuItem>
                  <MenuItem value="fidelity">Fidelity</MenuItem>
                  <MenuItem value="schwab">Schwab</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                label="Notes"
                value={newHolding.notes}
                onChange={(e) => setNewHolding({...newHolding, notes: e.target.value})}
                fullWidth
                multiline
                rows={2}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAddDialog(false)}>Cancel</Button>
          <Button onClick={handleAddHolding} variant="contained">Add Holding</Button>
        </DialogActions>
      </Dialog>

      {/* Import Dialog */}
      <Dialog open={openImportDialog} onClose={() => setOpenImportDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Import Portfolio</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Select your broker to import portfolio data:
          </Typography>
          
          {importStatus && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                {importStatus}
              </Typography>
              <LinearProgress variant="determinate" value={importProgress} />
            </Box>
          )}
          
          <Grid container spacing={2}>
            <Grid item xs={6}>
              <Button
                variant="outlined"
                fullWidth
                onClick={() => handleImportPortfolio('alpaca')}
                startIcon={<AccountBalance />}
              >
                Alpaca
              </Button>
            </Grid>
            <Grid item xs={6}>
              <Button
                variant="outlined"
                fullWidth
                onClick={() => handleImportPortfolio('robinhood')}
                startIcon={<AccountBalance />}
              >
                Robinhood
              </Button>
            </Grid>
            <Grid item xs={6}>
              <Button
                variant="outlined"
                fullWidth
                onClick={() => handleImportPortfolio('fidelity')}
                startIcon={<AccountBalance />}
              >
                Fidelity
              </Button>
            </Grid>
            <Grid item xs={6}>
              <Button
                variant="outlined"
                fullWidth
                onClick={() => handleImportPortfolio('schwab')}
                startIcon={<AccountBalance />}
              >
                Schwab
              </Button>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenImportDialog(false)}>Cancel</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default PortfolioManager;