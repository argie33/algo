/**
 * Crypto Portfolio Management Page
 * Comprehensive portfolio tracking with real-time data
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Grid,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  LinearProgress,
  Tab,
  Tabs
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  TrendingUp,
  TrendingDown,
  AccountBalanceWallet,
  Assessment,
  Timeline,
  Refresh
} from '@mui/icons-material';
import { PieChart, Pie, Cell, ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Legend, BarChart, Bar } from 'recharts';

const CryptoPortfolio = () => {
  const [portfolio, setPortfolio] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  
  // Dialog states
  const [addTransactionOpen, setAddTransactionOpen] = useState(false);
  const [transactionForm, setTransactionForm] = useState({
    symbol: '',
    name: '',
    type: 'buy',
    quantity: '',
    price: '',
    fee: '0',
    exchange: 'manual',
    notes: ''
  });
  
  const [cryptoOptions, setCryptoOptions] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  
  // Mock user ID - in production, get from auth context
  const userId = 'demo-user';
  
  // Fetch portfolio data
  const fetchPortfolio = useCallback(async () => {
    try {
      setRefreshing(true);
      const response = await fetch(`/api/crypto-portfolio/${userId}?vs_currency=usd`);
      const data = await response.json();
      
      if (data.success) {
        setPortfolio(data.data);
      } else {
        setError(data.error || 'Failed to fetch portfolio');
      }
    } catch (err) {
      console.error('Portfolio fetch error:', err);
      setError('Failed to fetch portfolio data');
    } finally {
      setRefreshing(false);
    }
  }, [userId]);
  
  // Fetch transactions
  const fetchTransactions = useCallback(async () => {
    try {
      const response = await fetch(`/api/crypto-portfolio/${userId}/transactions?limit=20`);
      const data = await response.json();
      
      if (data.success) {
        setTransactions(data.data.transactions || []);
      }
    } catch (err) {
      console.error('Transactions fetch error:', err);
    }
  }, [userId]);
  
  // Fetch analytics
  const fetchAnalytics = useCallback(async () => {
    try {
      const response = await fetch(`/api/crypto-portfolio/${userId}/analytics`);
      const data = await response.json();
      
      if (data.success) {
        setAnalytics(data.data);
      }
    } catch (err) {
      console.error('Analytics fetch error:', err);
    }
  }, [userId]);
  
  // Fetch crypto options for dropdown
  const fetchCryptoOptions = useCallback(async () => {
    try {
      const response = await fetch('/api/crypto/assets?per_page=100');
      const data = await response.json();
      
      if (data.success && data.data) {
        setCryptoOptions(data.data.map(crypto => ({
          id: crypto.id,
          symbol: crypto.symbol.toUpperCase(),
          name: crypto.name
        })));
      }
    } catch (err) {
      console.error('Crypto options fetch error:', err);
    }
  }, []);
  
  // Initial data load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        fetchPortfolio(),
        fetchTransactions(),
        fetchAnalytics(),
        fetchCryptoOptions()
      ]);
      setLoading(false);
    };
    
    loadData();
  }, [fetchPortfolio, fetchTransactions, fetchAnalytics, fetchCryptoOptions]);
  
  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchPortfolio, 30000);
    return () => clearInterval(interval);
  }, [fetchPortfolio]);
  
  // Handle transaction form submission
  const handleAddTransaction = async () => {
    try {
      const response = await fetch(`/api/crypto-portfolio/${userId}/transactions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...transactionForm,
          quantity: parseFloat(transactionForm.quantity),
          price: parseFloat(transactionForm.price),
          fee: parseFloat(transactionForm.fee || 0)
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        // Reset form
        setTransactionForm({
          symbol: '',
          name: '',
          type: 'buy',
          quantity: '',
          price: '',
          fee: '0',
          exchange: 'manual',
          notes: ''
        });
        setAddTransactionOpen(false);
        
        // Refresh data
        await Promise.all([fetchPortfolio(), fetchTransactions(), fetchAnalytics()]);
      } else {
        setError(data.error || 'Failed to add transaction');
      }
    } catch (err) {
      console.error('Add transaction error:', err);
      setError('Failed to add transaction');
    }
  };
  
  // Handle transaction deletion
  const handleDeleteTransaction = async (transactionId) => {
    try {
      const response = await fetch(`/api/crypto-portfolio/${userId}/transactions/${transactionId}?user_id=${userId}`, {
        method: 'DELETE'
      });
      
      const data = await response.json();
      
      if (data.success) {
        await Promise.all([fetchPortfolio(), fetchTransactions(), fetchAnalytics()]);
      } else {
        setError(data.error || 'Failed to delete transaction');
      }
    } catch (err) {
      console.error('Delete transaction error:', err);
      setError('Failed to delete transaction');
    }
  };
  
  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: amount < 1 ? 6 : 2
    }).format(amount);
  };
  
  // Color for profit/loss
  const getPnLColor = (value) => {
    if (value > 0) return '#4caf50';
    if (value < 0) return '#f44336';
    return '#666';
  };
  
  // Pie chart colors
  const PIE_COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D', '#FFC658', '#FF7C7C'];
  
  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" gutterBottom>
          Crypto Portfolio
        </Typography>
        <LinearProgress />
        <Typography sx={{ mt: 2 }}>Loading portfolio data...</Typography>
      </Box>
    );
  }
  
  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          Crypto Portfolio
        </Typography>
        <Box>
          <IconButton onClick={fetchPortfolio} disabled={refreshing}>
            <Refresh />
          </IconButton>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setAddTransactionOpen(true)}
            sx={{ ml: 1 }}
          >
            Add Transaction
          </Button>
        </Box>
      </Box>
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      
      {/* Portfolio Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <AccountBalanceWallet sx={{ color: '#1976d2', mr: 2 }} />
                <Box>
                  <Typography color="textSecondary" variant="body2">
                    Total Value
                  </Typography>
                  <Typography variant="h6">
                    {portfolio ? formatCurrency(portfolio.total_value) : '$0.00'}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Assessment sx={{ color: getPnLColor(portfolio?.total_pnl || 0), mr: 2 }} />
                <Box>
                  <Typography color="textSecondary" variant="body2">
                    Total P&L
                  </Typography>
                  <Typography variant="h6" sx={{ color: getPnLColor(portfolio?.total_pnl || 0) }}>
                    {portfolio ? formatCurrency(portfolio.total_pnl) : '$0.00'}
                  </Typography>
                  <Typography variant="body2" sx={{ color: getPnLColor(portfolio?.total_pnl_percentage || 0) }}>
                    {portfolio ? `${portfolio.total_pnl_percentage.toFixed(2)}%` : '0.00%'}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Timeline sx={{ color: getPnLColor(portfolio?.performance?.day_change || 0), mr: 2 }} />
                <Box>
                  <Typography color="textSecondary" variant="body2">
                    24h Change
                  </Typography>
                  <Typography variant="h6" sx={{ color: getPnLColor(portfolio?.performance?.day_change || 0) }}>
                    {portfolio ? formatCurrency(portfolio.performance.day_change) : '$0.00'}
                  </Typography>
                  <Typography variant="body2" sx={{ color: getPnLColor(portfolio?.performance?.day_change_percentage || 0) }}>
                    {portfolio ? `${portfolio.performance.day_change_percentage.toFixed(2)}%` : '0.00%'}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Assessment sx={{ color: '#1976d2', mr: 2 }} />
                <Box>
                  <Typography color="textSecondary" variant="body2">
                    Assets
                  </Typography>
                  <Typography variant="h6">
                    {portfolio?.holdings?.length || 0}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    {portfolio?.summary?.largest_holding?.symbol || 'N/A'} (largest)
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      
      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)}>
          <Tab label="Holdings" />
          <Tab label="Transactions" />
          <Tab label="Analytics" />
        </Tabs>
      </Box>
      
      {/* Tab Content */}
      {tabValue === 0 && (
        <Grid container spacing={3}>
          {/* Holdings Table */}
          <Grid item xs={12} lg={8}>
            <Card>
              <CardHeader title="Current Holdings" />
              <CardContent>
                {portfolio?.holdings?.length > 0 ? (
                  <TableContainer>
                    <Table>
                      <TableHead>
                        <TableRow>
                          <TableCell>Asset</TableCell>
                          <TableCell align="right">Quantity</TableCell>
                          <TableCell align="right">Avg Cost</TableCell>
                          <TableCell align="right">Current Price</TableCell>
                          <TableCell align="right">Value</TableCell>
                          <TableCell align="right">P&L</TableCell>
                          <TableCell align="right">24h Change</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {portfolio.holdings.map((holding) => (
                          <TableRow key={holding.symbol}>
                            <TableCell>
                              <Box>
                                <Typography variant="body2" fontWeight="bold">
                                  {holding.symbol.toUpperCase()}
                                </Typography>
                                <Typography variant="caption" color="textSecondary">
                                  {holding.name}
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              {holding.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                            </TableCell>
                            <TableCell align="right">
                              {formatCurrency(holding.average_cost)}
                            </TableCell>
                            <TableCell align="right">
                              {formatCurrency(holding.current_price)}
                            </TableCell>
                            <TableCell align="right">
                              {formatCurrency(holding.current_value)}
                            </TableCell>
                            <TableCell align="right">
                              <Box sx={{ color: getPnLColor(holding.unrealized_pnl) }}>
                                {formatCurrency(holding.unrealized_pnl)}
                                <br />
                                <Typography variant="caption">
                                  ({holding.unrealized_pnl_percentage.toFixed(2)}%)
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                                {holding.day_change > 0 ? <TrendingUp sx={{ color: '#4caf50', mr: 0.5 }} /> : <TrendingDown sx={{ color: '#f44336', mr: 0.5 }} />}
                                <Box sx={{ color: getPnLColor(holding.day_change) }}>
                                  {holding.day_change.toFixed(2)}%
                                </Box>
                              </Box>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Typography color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                    No holdings found. Add your first transaction to get started.
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
          
          {/* Allocation Chart */}
          <Grid item xs={12} lg={4}>
            <Card>
              <CardHeader title="Portfolio Allocation" />
              <CardContent>
                {portfolio?.allocation && Object.keys(portfolio.allocation).length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={Object.entries(portfolio.allocation).map(([symbol, data], index) => ({
                          name: symbol.toUpperCase(),
                          value: data.percentage,
                          color: PIE_COLORS[index % PIE_COLORS.length]
                        }))}
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="value"
                        label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                      >
                        {Object.entries(portfolio.allocation).map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                    No allocation data available
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
      
      {tabValue === 1 && (
        <Card>
          <CardHeader title="Transaction History" />
          <CardContent>
            {transactions.length > 0 ? (
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Date</TableCell>
                      <TableCell>Asset</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell align="right">Quantity</TableCell>
                      <TableCell align="right">Price</TableCell>
                      <TableCell align="right">Total</TableCell>
                      <TableCell align="right">Fee</TableCell>
                      <TableCell>Exchange</TableCell>
                      <TableCell align="center">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {transactions.map((transaction) => (
                      <TableRow key={transaction.id}>
                        <TableCell>
                          <Typography variant="body2">
                            {transaction.formatted_date}
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            {transaction.formatted_time}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {transaction.symbol.toUpperCase()}
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            {transaction.name}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={transaction.type.toUpperCase()} 
                            size="small"
                            color={transaction.type === 'buy' ? 'success' : 'error'}
                          />
                        </TableCell>
                        <TableCell align="right">
                          {transaction.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                        </TableCell>
                        <TableCell align="right">
                          {transaction.formatted_price}
                        </TableCell>
                        <TableCell align="right">
                          {transaction.formatted_total}
                        </TableCell>
                        <TableCell align="right">
                          {formatCurrency(transaction.fee)}
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            {transaction.exchange}
                          </Typography>
                        </TableCell>
                        <TableCell align="center">
                          <Tooltip title="Delete Transaction">
                            <IconButton 
                              size="small" 
                              onClick={() => handleDeleteTransaction(transaction.id)}
                              color="error"
                            >
                              <DeleteIcon />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                No transactions found. Add your first transaction to get started.
              </Typography>
            )}
          </CardContent>
        </Card>
      )}
      
      {tabValue === 2 && analytics && (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Risk Metrics" />
              <CardContent>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">
                    Diversification Score
                  </Typography>
                  <Typography variant="h6">
                    {analytics.risk_metrics?.diversification_score || 'N/A'}
                  </Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">
                    Concentration Risk
                  </Typography>
                  <Typography variant="h6">
                    {analytics.risk_metrics?.concentration_risk?.toFixed(1) || '0'}%
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="textSecondary">
                    Largest Position
                  </Typography>
                  <Typography variant="h6">
                    {analytics.risk_metrics?.largest_position || 'N/A'}
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Performance Summary" />
              <CardContent>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">
                    Total Return
                  </Typography>
                  <Typography variant="h6" sx={{ color: getPnLColor(analytics.total_return_percentage) }}>
                    {analytics.total_return_percentage?.toFixed(2) || '0.00'}%
                  </Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">
                    Realized P&L
                  </Typography>
                  <Typography variant="h6" sx={{ color: getPnLColor(analytics.realized_pnl) }}>
                    {formatCurrency(analytics.realized_pnl || 0)}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="textSecondary">
                    Portfolio Age
                  </Typography>
                  <Typography variant="h6">
                    {analytics.performance_summary?.portfolio_age_days || 0} days
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
      
      {/* Add Transaction Dialog */}
      <Dialog open={addTransactionOpen} onClose={() => setAddTransactionOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Add Transaction</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                select
                fullWidth
                label="Cryptocurrency"
                value={transactionForm.symbol}
                onChange={(e) => {
                  const selectedCrypto = cryptoOptions.find(crypto => crypto.id === e.target.value);
                  setTransactionForm({
                    ...transactionForm,
                    symbol: e.target.value,
                    name: selectedCrypto?.name || ''
                  });
                }}
              >
                {cryptoOptions.map((crypto) => (
                  <MenuItem key={crypto.id} value={crypto.id}>
                    {crypto.symbol} - {crypto.name}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                select
                fullWidth
                label="Type"
                value={transactionForm.type}
                onChange={(e) => setTransactionForm({...transactionForm, type: e.target.value})}
              >
                <MenuItem value="buy">Buy</MenuItem>
                <MenuItem value="sell">Sell</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Quantity"
                type="number"
                value={transactionForm.quantity}
                onChange={(e) => setTransactionForm({...transactionForm, quantity: e.target.value})}
                inputProps={{ step: "any", min: "0" }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Price per Unit"
                type="number"
                value={transactionForm.price}
                onChange={(e) => setTransactionForm({...transactionForm, price: e.target.value})}
                inputProps={{ step: "any", min: "0" }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Fee"
                type="number"
                value={transactionForm.fee}
                onChange={(e) => setTransactionForm({...transactionForm, fee: e.target.value})}
                inputProps={{ step: "any", min: "0" }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Exchange"
                value={transactionForm.exchange}
                onChange={(e) => setTransactionForm({...transactionForm, exchange: e.target.value})}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Notes (optional)"
                multiline
                rows={2}
                value={transactionForm.notes}
                onChange={(e) => setTransactionForm({...transactionForm, notes: e.target.value})}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddTransactionOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleAddTransaction} 
            variant="contained"
            disabled={!transactionForm.symbol || !transactionForm.quantity || !transactionForm.price}
          >
            Add Transaction
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CryptoPortfolio;