import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  TableContainer,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  IconButton,
  Chip,
  Alert,
  MenuItem,
  LinearProgress,
  Tooltip
} from '@mui/material';
import {
  Add,
  Edit,
  Delete,
  TrendingUp,
  TrendingDown,
  AccountBalanceWallet,
  Assessment,
  PieChart,
  Refresh
} from '@mui/icons-material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Pie } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip as ChartTooltip,
  Legend
} from 'chart.js';

import { LoadingDisplay } from '../components/LoadingDisplay';
import ErrorBoundary from '../components/ErrorBoundary';
import apiService from '../utils/apiService.jsx';
import { useAuth } from '../contexts/AuthContext';

// Register Chart.js components
ChartJS.register(ArcElement, ChartTooltip, Legend);

function CryptoPortfolio() {
  const [addPositionOpen, setAddPositionOpen] = useState(false);
  const [editingPosition, setEditingPosition] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [newPosition, setNewPosition] = useState({
    symbol: '',
    quantity: '',
    purchase_price: '',
    purchase_date: new Date().toISOString().split('T')[0]
  });

  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();

  console.log('💼 [CRYPTO-PORTFOLIO] Rendering crypto portfolio page');

  // Fetch portfolio data
  const { 
    data: portfolioData, 
    isLoading: portfolioLoading, 
    error: portfolioError,
    refetch: refetchPortfolio 
  } = useQuery({
    queryKey: ['cryptoPortfolio', refreshKey],
    queryFn: () => apiService.get('/crypto/portfolio'),
    refetchInterval: 60000, // Refresh every minute
    staleTime: 50000,
    cacheTime: 120000,
    enabled: isAuthenticated
  });

  // Add position mutation
  const addPositionMutation = useMutation({
    mutationFn: (positionData) => apiService.post('/crypto/portfolio/add', positionData),
    onSuccess: () => {
      queryClient.invalidateQueries(['cryptoPortfolio']);
      setAddPositionOpen(false);
      resetNewPosition();
      console.log('✅ [CRYPTO-PORTFOLIO] Position added successfully');
    },
    onError: (error) => {
      console.error('❌ [CRYPTO-PORTFOLIO] Failed to add position:', error);
    }
  });

  const resetNewPosition = () => {
    setNewPosition({
      symbol: '',
      quantity: '',
      purchase_price: '',
      purchase_date: new Date().toISOString().split('T')[0]
    });
  };

  const handleAddPosition = () => {
    if (!newPosition.symbol || !newPosition.quantity || !newPosition.purchase_price) {
      return;
    }

    const positionData = {
      symbol: newPosition.symbol.toUpperCase(),
      quantity: parseFloat(newPosition.quantity),
      purchase_price: parseFloat(newPosition.purchase_price),
      purchase_date: newPosition.purchase_date
    };

    console.log('➕ [CRYPTO-PORTFOLIO] Adding new position:', positionData);
    addPositionMutation.mutate(positionData);
  };

  const handleRefresh = () => {
    console.log('🔄 [CRYPTO-PORTFOLIO] Manual refresh triggered');
    setRefreshKey(prev => prev + 1);
    refetchPortfolio();
  };

  const formatCurrency = (value, decimals = 2) => {
    if (!value && value !== 0) return 'N/A';
    
    if (Math.abs(value) >= 1000000000) {
      return `$${(value / 1000000000).toFixed(1)}B`;
    } else if (Math.abs(value) >= 1000000) {
      return `$${(value / 1000000).toFixed(1)}M`;
    } else if (Math.abs(value) >= 1000) {
      return `$${(value / 1000).toFixed(1)}K`;
    } else {
      return `$${Number(value).toFixed(decimals)}`;
    }
  };

  const formatPercentage = (value, showSign = true) => {
    if (!value && value !== 0) return 'N/A';
    const formatted = `${Math.abs(value).toFixed(2)}%`;
    if (!showSign) return formatted;
    return value >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  const getPercentageColor = (value) => {
    if (!value && value !== 0) return 'text.secondary';
    return value >= 0 ? 'success.main' : 'error.main';
  };

  const getPercentageIcon = (value) => {
    if (!value && value !== 0) return null;
    return value >= 0 ? <TrendingUp fontSize="small" /> : <TrendingDown fontSize="small" />;
  };

  const generateChartColors = (count) => {
    const colors = [
      '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
      '#FF9F40', '#FF6384', '#C9CBCF', '#4BC0C0', '#FF6384'
    ];
    return colors.slice(0, count);
  };

  const renderPortfolioSummary = () => {
    if (!portfolioData?.data?.portfolio_summary) return null;

    const summary = portfolioData.data.portfolio_summary;

    return (
      <Grid container spacing={3} mb={3}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Total Value</Typography>
              <Typography variant="h4" color="primary">
                {formatCurrency(summary.total_value)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Current Portfolio Value
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Total Cost</Typography>
              <Typography variant="h4">
                {formatCurrency(summary.total_cost)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Total Investment
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>P&L</Typography>
              <Box display="flex" alignItems="center">
                {getPercentageIcon(summary.total_pnl)}
                <Typography 
                  variant="h4" 
                  color={getPercentageColor(summary.total_pnl)}
                  sx={{ ml: 0.5 }}
                >
                  {formatCurrency(summary.total_pnl)}
                </Typography>
              </Box>
              <Typography 
                variant="body2" 
                color={getPercentageColor(summary.total_pnl_percentage)}
              >
                {formatPercentage(summary.total_pnl_percentage)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Positions</Typography>
              <Typography variant="h4" color="primary">
                {summary.positions_count}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Active Holdings
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  const renderAllocationChart = () => {
    if (!portfolioData?.data?.positions || portfolioData.data.positions.length === 0) return null;

    const positions = portfolioData.data.positions;
    const chartData = {
      labels: positions.map(pos => pos.symbol),
      datasets: [{
        data: positions.map(pos => pos.allocation_percentage),
        backgroundColor: generateChartColors(positions.length),
        borderWidth: 2,
        borderColor: '#fff'
      }]
    };

    const chartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'right',
          labels: {
            usePointStyle: true,
            padding: 20
          }
        },
        tooltip: {
          callbacks: {
            label: (context) => {
              const position = positions[context.dataIndex];
              return `${position.symbol}: ${position.allocation_percentage}% (${formatCurrency(position.current_value)})`;
            }
          }
        }
      }
    };

    return (
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Portfolio Allocation
          </Typography>
          <Box sx={{ height: 300, position: 'relative' }}>
            <Pie data={chartData} options={chartOptions} />
          </Box>
        </CardContent>
      </Card>
    );
  };

  const renderPositionsTable = () => {
    if (!portfolioData?.data?.positions || portfolioData.data.positions.length === 0) {
      return (
        <Card>
          <CardContent>
            <Alert severity="info">
              No cryptocurrency positions found. Add your first position to get started!
            </Alert>
          </CardContent>
        </Card>
      );
    }

    const positions = portfolioData.data.positions;

    return (
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Asset</TableCell>
              <TableCell align="right">Quantity</TableCell>
              <TableCell align="right">Purchase Price</TableCell>
              <TableCell align="right">Current Price</TableCell>
              <TableCell align="right">Current Value</TableCell>
              <TableCell align="right">P&L</TableCell>
              <TableCell align="right">P&L %</TableCell>
              <TableCell align="right">Allocation</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {positions.map((position, index) => (
              <TableRow key={`${position.symbol}-${index}`} hover>
                <TableCell>
                  <Box>
                    <Typography variant="subtitle2" fontWeight="bold">
                      {position.symbol}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Purchased: {new Date(position.purchase_date).toLocaleDateString()}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {position.quantity?.toLocaleString()}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {formatCurrency(position.purchase_price)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2">
                    {formatCurrency(position.current_price)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" fontWeight="medium">
                    {formatCurrency(position.current_value)}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Box display="flex" alignItems="center" justifyContent="flex-end">
                    {getPercentageIcon(position.pnl)}
                    <Typography 
                      variant="body2" 
                      color={getPercentageColor(position.pnl)}
                      sx={{ ml: 0.5, fontWeight: 'medium' }}
                    >
                      {formatCurrency(position.pnl)}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Box display="flex" alignItems="center" justifyContent="flex-end">
                    {getPercentageIcon(position.pnl_percentage)}
                    <Typography 
                      variant="body2" 
                      color={getPercentageColor(position.pnl_percentage)}
                      sx={{ ml: 0.5, fontWeight: 'medium' }}
                    >
                      {formatPercentage(position.pnl_percentage)}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Box display="flex" alignItems="center" justifyContent="flex-end">
                    <LinearProgress 
                      variant="determinate" 
                      value={position.allocation_percentage} 
                      sx={{ width: 60, mr: 1 }}
                    />
                    <Typography variant="body2">
                      {position.allocation_percentage?.toFixed(1)}%
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell align="center">
                  <Tooltip title="Edit Position">
                    <IconButton size="small" onClick={() => setEditingPosition(position)}>
                      <Edit fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Remove Position">
                    <IconButton size="small" color="error">
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    );
  };

  if (!isAuthenticated) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          Please sign in to view your crypto portfolio.
        </Alert>
      </Box>
    );
  }

  if (portfolioLoading) {
    return <LoadingDisplay message="Loading your crypto portfolio..." />;
  }

  if (portfolioError) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">
          Failed to load portfolio data: {portfolioError.message}
        </Alert>
      </Box>
    );
  }

  return (
    <ErrorBoundary fallback={<Alert severity="error">Failed to load crypto portfolio</Alert>}>
      <Box sx={{ width: '100%', p: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
          <Typography variant="h4" component="h1">
            Crypto Portfolio
          </Typography>
          
          <Box display="flex" gap={2}>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={handleRefresh}
            >
              Refresh
            </Button>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setAddPositionOpen(true)}
            >
              Add Position
            </Button>
          </Box>
        </Box>

        {/* Portfolio Summary */}
        {renderPortfolioSummary()}

        <Grid container spacing={3}>
          {/* Allocation Chart */}
          <Grid item xs={12} lg={4}>
            {renderAllocationChart()}
          </Grid>

          {/* Positions Table */}
          <Grid item xs={12} lg={8}>
            {renderPositionsTable()}
          </Grid>
        </Grid>

        {/* Add Position Dialog */}
        <Dialog 
          open={addPositionOpen} 
          onClose={() => setAddPositionOpen(false)}
          maxWidth="sm"
          fullWidth
        >
          <DialogTitle>Add Cryptocurrency Position</DialogTitle>
          <DialogContent>
            <Box sx={{ pt: 2 }}>
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <TextField
                    select
                    fullWidth
                    label="Cryptocurrency"
                    value={newPosition.symbol}
                    onChange={(e) => setNewPosition(prev => ({ ...prev, symbol: e.target.value }))}
                  >
                    {['BTC', 'ETH', 'SOL', 'AVAX', 'MATIC', 'DOT', 'LINK', 'UNI', 'AAVE', 'CRV'].map(symbol => (
                      <MenuItem key={symbol} value={symbol}>
                        {symbol}
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
                
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Quantity"
                    type="number"
                    value={newPosition.quantity}
                    onChange={(e) => setNewPosition(prev => ({ ...prev, quantity: e.target.value }))}
                    placeholder="0.00"
                    inputProps={{ step: "0.000001", min: "0" }}
                  />
                </Grid>
                
                <Grid item xs={12} sm={6}>
                  <TextField
                    fullWidth
                    label="Purchase Price (USD)"
                    type="number"
                    value={newPosition.purchase_price}
                    onChange={(e) => setNewPosition(prev => ({ ...prev, purchase_price: e.target.value }))}
                    placeholder="0.00"
                    inputProps={{ step: "0.01", min: "0" }}
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Purchase Date"
                    type="date"
                    value={newPosition.purchase_date}
                    onChange={(e) => setNewPosition(prev => ({ ...prev, purchase_date: e.target.value }))}
                    InputLabelProps={{ shrink: true }}
                  />
                </Grid>
              </Grid>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setAddPositionOpen(false)}>
              Cancel
            </Button>
            <Button 
              onClick={handleAddPosition}
              variant="contained"
              disabled={addPositionMutation.isLoading || !newPosition.symbol || !newPosition.quantity || !newPosition.purchase_price}
            >
              {addPositionMutation.isLoading ? 'Adding...' : 'Add Position'}
            </Button>
          </DialogActions>
        </Dialog>
      </Box>
    </ErrorBoundary>
  );
}

export default CryptoPortfolio;