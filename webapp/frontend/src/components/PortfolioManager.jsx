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
      
      const data = await getPortfolioData();
      setPortfolioData(data);
      
      // Calculate portfolio summary
      calculatePortfolioSummary(data);
      
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
    return `${percent >= 0 ? '+' : ''}${percent.toFixed(2)}%`;
  };

  const getChangeColor = (change) => {
    if (change > 0) return 'success.main';
    if (change < 0) return 'error.main';
    return 'text.secondary';
  };

  if (loading) {
    return (
      <div  display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div>
      {/* API Key Status */}
      <div  sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          compact={true}
          showSetupDialog={true}
          onStatusChange={(status) => {
            console.log('Portfolio Manager - API Key Status:', status);
          }}
        />
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
          {error}
        </div>
      )}

      {/* Portfolio Summary Cards */}
      <div className="grid" container spacing={3} sx={{ mb: 3 }}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Total Value
              </div>
              <div  variant="h4" color="primary.main">
                {formatCurrency(portfolioSummary.totalValue)}
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Total Gain/Loss
              </div>
              <div  
                variant="h4" 
                color={getChangeColor(portfolioSummary.totalGainLoss)}
                sx={{ display: 'flex', alignItems: 'center' }}
              >
                {portfolioSummary.totalGainLoss >= 0 ? <TrendingUp /> : <TrendingDown />}
                {formatCurrency(portfolioSummary.totalGainLoss)}
              </div>
              <div  variant="body2" color="text.secondary">
                {formatPercent(portfolioSummary.totalGainLossPercent)}
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Top Performer
              </div>
              {portfolioSummary.topGainer ? (
                <>
                  <div  variant="h5" color="success.main">
                    {portfolioSummary.topGainer.symbol}
                  </div>
                  <div  variant="body2" color="text.secondary">
                    {formatPercent(portfolioSummary.topGainer.gainLossPercent)}
                  </div>
                </>
              ) : (
                <div  variant="body2" color="text.secondary">
                  No data
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Risk Metrics
              </div>
              <div  variant="body2">
                Beta: {portfolioSummary.riskMetrics.beta.toFixed(2)}
              </div>
              <div  variant="body2">
                Sharpe: {portfolioSummary.riskMetrics.sharpeRatio.toFixed(2)}
              </div>
              <div  variant="body2">
                Volatility: {portfolioSummary.riskMetrics.volatility.toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div  sx={{ mb: 3, display: 'flex', gap: 2 }}>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          variant="contained"
          startIcon={<Add />}
          onClick={() => setOpenAddDialog(true)}
        >
          Add Holding
        </button>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          variant="outlined"
          startIcon={<CloudSync />}
          onClick={() => setOpenImportDialog(true)}
        >
          Import from Broker
        </button>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          variant="outlined"
          startIcon={<Refresh />}
          onClick={fetchPortfolioData}
        >
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200" value={tabValue} onChange={(e, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Holdings" />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Allocation" />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Performance" />
      </div>

      {/* Holdings Table */}
      {tabValue === 0 && (
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Quantity</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Avg Price</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Current Price</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Market Value</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Gain/Loss</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Gain/Loss %</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
              </tr>
            </thead>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
              {portfolioData.map((holding) => (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={holding.id}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                    <div>
                      <div  variant="body2" fontWeight="bold">
                        {holding.symbol}
                      </div>
                      <div  variant="caption" color="text.secondary">
                        {holding.companyName}
                      </div>
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{holding.quantity}</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatCurrency(holding.averagePrice)}</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatCurrency(holding.currentPrice)}</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatCurrency(holding.currentValue)}</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    <div  color={getChangeColor(holding.gainLoss)}>
                      {formatCurrency(holding.gainLoss)}
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                      label={formatPercent(holding.gainLossPercent)}
                      color={holding.gainLossPercent >= 0 ? 'success' : 'error'}
                      size="small"
                    />
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                    <button className="p-2 rounded-full hover:bg-gray-100"
                      onClick={() => {
                        setSelectedHolding(holding);
                        setOpenEditDialog(true);
                      }}
                    >
                      <Edit />
                    </button>
                    <button className="p-2 rounded-full hover:bg-gray-100"
                      onClick={() => handleDeleteHolding(holding.id)}
                      color="error"
                    >
                      <Delete />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Sector Allocation */}
      {tabValue === 1 && (
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={6}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>
                  Sector Allocation
                </div>
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
              </div>
            </div>
          </div>
          
          <div className="grid" item xs={12} md={6}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>
                  Top Holdings
                </div>
                {portfolioData
                  .sort((a, b) => b.currentValue - a.currentValue)
                  .slice(0, 5)
                  .map((holding) => (
                    <div  key={holding.id} sx={{ mb: 2 }}>
                      <div  display="flex" justifyContent="space-between" alignItems="center">
                        <div  variant="body2">{holding.symbol}</div>
                        <div  variant="body2">
                          {formatCurrency(holding.currentValue)}
                        </div>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2"
                        variant="determinate"
                        value={(holding.currentValue / portfolioSummary.totalValue) * 100}
                        sx={{ mt: 1 }}
                      />
                    </div>
                  ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Holding Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={openAddDialog} onClose={() => setOpenAddDialog(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Add New Holding</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div className="grid" container spacing={2} sx={{ mt: 1 }}>
            <div className="grid" item xs={12}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Symbol"
                value={newHolding.symbol}
                onChange={(e) => setNewHolding({...newHolding, symbol: e.target.value.toUpperCase()})}
                fullWidth
                required
              />
            </div>
            <div className="grid" item xs={6}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Quantity"
                type="number"
                value={newHolding.quantity}
                onChange={(e) => setNewHolding({...newHolding, quantity: e.target.value})}
                fullWidth
                required
              />
            </div>
            <div className="grid" item xs={6}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Average Price"
                type="number"
                value={newHolding.averagePrice}
                onChange={(e) => setNewHolding({...newHolding, averagePrice: e.target.value})}
                fullWidth
                required
              />
            </div>
            <div className="grid" item xs={6}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Purchase Date"
                type="date"
                value={newHolding.purchaseDate}
                onChange={(e) => setNewHolding({...newHolding, purchaseDate: e.target.value})}
                fullWidth
                InputLabelProps={{ shrink: true }}
              />
            </div>
            <div className="grid" item xs={6}>
              <div className="mb-4" fullWidth>
                <label className="block text-sm font-medium text-gray-700 mb-1">Broker</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={newHolding.broker}
                  onChange={(e) => setNewHolding({...newHolding, broker: e.target.value})}
                >
                  <option  value="manual">Manual Entry</option>
                  <option  value="alpaca">Alpaca</option>
                  <option  value="robinhood">Robinhood</option>
                  <option  value="fidelity">Fidelity</option>
                  <option  value="schwab">Schwab</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Notes"
                value={newHolding.notes}
                onChange={(e) => setNewHolding({...newHolding, notes: e.target.value})}
                fullWidth
                multiline
                rows={2}
              />
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setOpenAddDialog(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleAddHolding} variant="contained">Add Holding</button>
        </div>
      </div>

      {/* Import Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={openImportDialog} onClose={() => setOpenImportDialog(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Import Portfolio</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div  variant="body2" sx={{ mb: 2 }}>
            Select your broker to import portfolio data:
          </div>
          
          {importStatus && (
            <div  sx={{ mb: 2 }}>
              <div  variant="body2" sx={{ mb: 1 }}>
                {importStatus}
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" variant="determinate" value={importProgress} />
            </div>
          )}
          
          <div className="grid" container spacing={2}>
            <div className="grid" item xs={6}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                fullWidth
                onClick={() => handleImportPortfolio('alpaca')}
                startIcon={<AccountBalance />}
              >
                Alpaca
              </button>
            </div>
            <div className="grid" item xs={6}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                fullWidth
                onClick={() => handleImportPortfolio('robinhood')}
                startIcon={<AccountBalance />}
              >
                Robinhood
              </button>
            </div>
            <div className="grid" item xs={6}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                fullWidth
                onClick={() => handleImportPortfolio('fidelity')}
                startIcon={<AccountBalance />}
              >
                Fidelity
              </button>
            </div>
            <div className="grid" item xs={6}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                fullWidth
                onClick={() => handleImportPortfolio('schwab')}
                startIcon={<AccountBalance />}
              >
                Schwab
              </button>
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setOpenImportDialog(false)}>Cancel</button>
        </div>
      </div>
    </div>
  );
};

export default PortfolioManager;