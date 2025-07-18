import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
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
  LinearProgress,
  Fab,
  TableSortLabel,
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
  Treemap
} from 'recharts';
import {
  Add,
  Delete,
  Edit,
  TrendingUp,
  TrendingDown,
  AccountBalance,
  PieChart as PieChartIcon,
  Download,
  Upload,
  Sync,
  FilterList
} from '@mui/icons-material';
import { getPortfolioData, addHolding, updateHolding, deleteHolding, importPortfolioFromBroker } from '../services/api';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

const PortfolioHoldings = () => {
  const { user } = useAuth();
  const [holdings, setHoldings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [selectedHolding, setSelectedHolding] = useState(null);
  const [orderBy, setOrderBy] = useState('marketValue');
  const [order, setOrder] = useState('desc');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [filterText, setFilterText] = useState('');

  // New holding form state
  const [newHolding, setNewHolding] = useState({
    symbol: '',
    quantity: '',
    costBasis: '',
    purchaseDate: new Date().toISOString().split('T')[0]
  });

  const [portfolioSummary, setPortfolioSummary] = useState({
    totalValue: 0,
    totalCost: 0,
    totalGainLoss: 0,
    totalGainLossPercent: 0,
    dayGainLoss: 0,
    dayGainLossPercent: 0,
    cashBalance: 0
  });

  useEffect(() => {
    fetchHoldings();
  }, []);

  const fetchHoldings = async () => {
    try {
      setLoading(true);
      const response = await getPortfolioData();
      
      // Handle both direct data and wrapped response structures
      const data = response?.data || response;
      
      if (data?.holdings && Array.isArray(data.holdings)) {
        // Transform API data to component format
        const transformedHoldings = data.holdings.map(holding => ({
          id: holding.id || holding.symbol,
          symbol: holding.symbol,
          companyName: holding.name || holding.company || holding.companyName,
          quantity: holding.quantity,
          costBasis: holding.avgCost || holding.cost_basis || holding.averageEntryPrice || holding.average_entry_price,
          currentPrice: holding.currentPrice || holding.current_price,
          marketValue: holding.marketValue || holding.market_value,
          gainLoss: holding.unrealizedPnl || holding.pnl || holding.gainLoss,
          gainLossPercent: holding.unrealizedPnlPercent || holding.pnl_percent || holding.gainLossPercent,
          dayChange: holding.dayChange || holding.day_change,
          dayChangePercent: holding.dayChangePercent || holding.day_change_percent,
          sector: holding.sector,
          weight: holding.weight,
          purchaseDate: holding.purchaseDate
        }));
        
        setHoldings(transformedHoldings);
        
        // Transform summary data
        const transformedSummary = {
          totalValue: data.summary?.totalValue || data.totalValue || transformedHoldings.reduce((sum, h) => sum + (h.marketValue || 0), 0),
          totalCost: data.summary?.totalCost || transformedHoldings.reduce((sum, h) => sum + ((h.costBasis || 0) * (h.quantity || 0)), 0),
          totalGainLoss: data.summary?.totalPnl || data.summary?.totalGainLoss || transformedHoldings.reduce((sum, h) => sum + (h.gainLoss || 0), 0),
          totalGainLossPercent: data.summary?.totalPnlPercent || data.summary?.totalGainLossPercent || 0,
          dayGainLoss: data.summary?.dayPnl || data.summary?.dayGainLoss || transformedHoldings.reduce((sum, h) => sum + (h.dayChange || 0), 0),
          dayGainLossPercent: data.summary?.dayPnlPercent || data.summary?.dayGainLossPercent || 0,
          cashBalance: data.summary?.cash || data.summary?.cashBalance || 0
        };
        
        setPortfolioSummary(transformedSummary);
      } else {
        // If no holdings data, show empty state
        setHoldings([]);
        setPortfolioSummary({
          totalValue: 0,
          totalCost: 0,
          totalGainLoss: 0,
          totalGainLossPercent: 0,
          dayGainLoss: 0,
          dayGainLossPercent: 0,
          cashBalance: 0
        });
      }
    } catch (err) {
      console.error('Holdings fetch error:', err);
      setError('Failed to fetch portfolio holdings');
      
      // Set empty state on error
      setHoldings([]);
      setPortfolioSummary({
        totalValue: 0,
        totalCost: 0,
        totalGainLoss: 0,
        totalGainLossPercent: 0,
        dayGainLoss: 0,
        dayGainLossPercent: 0,
        cashBalance: 0
      });
    } finally {
      setLoading(false);
    }
  };

  const handleAddHolding = async () => {
    try {
      if (!newHolding.symbol || !newHolding.quantity || !newHolding.costBasis) {
        setError('Please fill in all required fields');
        return;
      }

      await addHolding({
        ...newHolding,
        quantity: parseFloat(newHolding.quantity),
        costBasis: parseFloat(newHolding.costBasis)
      });

      setAddDialogOpen(false);
      setNewHolding({ symbol: '', quantity: '', costBasis: '', purchaseDate: new Date().toISOString().split('T')[0] });
      fetchHoldings();
    } catch (err) {
      setError('Failed to add holding');
      console.error('Add holding error:', err);
    }
  };

  const handleEditHolding = async () => {
    try {
      await updateHolding(selectedHolding.id, {
        quantity: parseFloat(selectedHolding.quantity),
        costBasis: parseFloat(selectedHolding.costBasis),
        purchaseDate: selectedHolding.purchaseDate
      });

      setEditDialogOpen(false);
      setSelectedHolding(null);
      fetchHoldings();
    } catch (err) {
      setError('Failed to update holding');
      console.error('Update holding error:', err);
    }
  };

  const handleDeleteHolding = async (holdingId) => {
    try {
      await deleteHolding(holdingId);
      fetchHoldings();
    } catch (err) {
      setError('Failed to delete holding');
      console.error('Delete holding error:', err);
    }
  };

  const handleImportFromBroker = async (broker) => {
    try {
      setLoading(true);
      await importPortfolioFromBroker(broker);
      setImportDialogOpen(false);
      fetchHoldings();
    } catch (err) {
      setError(`Failed to import from ${broker}`);
      console.error('Import error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRequestSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
  };

  const getSectorColor = (sector) => {
    const colors = {
      'Technology': '#2196F3',
      'Healthcare': '#4CAF50',
      'Financial': '#FF9800',
      'Consumer': '#9C27B0',
      'Industrial': '#795548',
      'Energy': '#F44336',
      'Utilities': '#607D8B',
      'Materials': '#3F51B5',
      'Real Estate': '#E91E63',
      'Communication': '#00BCD4'
    };
    return colors[sector] || '#9E9E9E';
  };

  const filteredHoldings = holdings.filter(holding =>
    holding.symbol.toLowerCase().includes(filterText.toLowerCase()) ||
    holding.companyName?.toLowerCase().includes(filterText.toLowerCase()) ||
    holding.sector?.toLowerCase().includes(filterText.toLowerCase())
  );

  const sortedHoldings = [...filteredHoldings].sort((a, b) => {
    let aValue = a[orderBy];
    let bValue = b[orderBy];

    if (typeof aValue === 'string') {
      aValue = aValue.toLowerCase();
      bValue = bValue.toLowerCase();
    }

    if (order === 'desc') {
      return bValue > aValue ? 1 : -1;
    }
    return aValue > bValue ? 1 : -1;
  });

  const paginatedHoldings = sortedHoldings.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  // Prepare sector allocation data
  const sectorAllocation = holdings.reduce((acc, holding) => {
    const sector = holding.sector || 'Unknown';
    if (!acc[sector]) {
      acc[sector] = { value: 0, count: 0 };
    }
    acc[sector].value += holding.marketValue || 0;
    acc[sector].count += 1;
    return acc;
  }, {});

  const sectorData = Object.entries(sectorAllocation).map(([sector, data]) => ({
    name: sector,
    value: data.value,
    count: data.count,
    percentage: ((data.value / portfolioSummary.totalValue) * 100).toFixed(1)
  }));

  // Top holdings for treemap
  const topHoldings = holdings
    .sort((a, b) => (b.marketValue || 0) - (a.marketValue || 0))
    .slice(0, 10)
    .map(holding => ({
      name: holding.symbol,
      size: holding.marketValue || 0,
      gainLoss: holding.gainLoss || 0
    }));

  if (loading) {
    return (
      <div className="container mx-auto" maxWidth="xl">
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="xl">
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" gutterBottom>
          Portfolio Holdings
        </div>
        <div  variant="body1" color="text.secondary">
          Track and manage your investment holdings
        </div>
      </div>

      {/* API Key Status */}
      <div  sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          showSetupDialog={true}
          onStatusChange={(status) => {
            console.log('Portfolio Holdings - API Key Status:', status);
          }}
        />
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </div>
      )}

      {/* Portfolio Summary Cards */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  color="text.secondary" gutterBottom>
                Total Value
              </div>
              <div  variant="h5">
                ${portfolioSummary.totalValue.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  color="text.secondary" gutterBottom>
                Total Gain/Loss
              </div>
              <div  
                variant="h5" 
                color={portfolioSummary.totalGainLoss >= 0 ? 'success.main' : 'error.main'}
              >
                ${portfolioSummary.totalGainLoss.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
              <div  
                variant="body2" 
                color={portfolioSummary.totalGainLoss >= 0 ? 'success.main' : 'error.main'}
              >
                ({portfolioSummary.totalGainLossPercent.toFixed(2)}%)
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  color="text.secondary" gutterBottom>
                Day Gain/Loss
              </div>
              <div  
                variant="h5" 
                color={portfolioSummary.dayGainLoss >= 0 ? 'success.main' : 'error.main'}
              >
                ${portfolioSummary.dayGainLoss.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
              <div  
                variant="body2" 
                color={portfolioSummary.dayGainLoss >= 0 ? 'success.main' : 'error.main'}
              >
                ({portfolioSummary.dayGainLossPercent.toFixed(2)}%)
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  color="text.secondary" gutterBottom>
                Cash Balance
              </div>
              <div  variant="h5">
                ${portfolioSummary.cashBalance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Sector Allocation
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={sectorData}
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                    label={({ name, percentage }) => `${name} ${percentage}%`}
                  >
                    {sectorData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={getSectorColor(entry.name)} />
                    ))}
                  </Pie>
                  <RechartsTooltip formatter={(value) => [`$${value.toLocaleString()}`, 'Value']} />
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
              <ResponsiveContainer width="100%" height={300}>
                <Treemap
                  data={topHoldings}
                  dataKey="size"
                  aspectRatio={4/3}
                  stroke="#fff"
                  fill="#8884d8"
                />
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      {/* Actions Bar */}
      <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <div  sx={{ display: 'flex', gap: 1 }}>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAddDialogOpen(true)}
          >
            Add Holding
          </button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Upload />}
            onClick={() => setImportDialogOpen(true)}
          >
            Import
          </button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Sync />}
            onClick={fetchHoldings}
          >
            Refresh
          </button>
        </div>
        <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          size="small"
          placeholder="Filter holdings..."
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          InputProps={{
            startAdornment: <FilterList sx={{ mr: 1, color: 'text.secondary' }} />
          }}
        />
      </div>

      {/* Holdings Table */}
      <div className="bg-white shadow-md rounded-lg">
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leSortLabel
                    active={orderBy === 'symbol'}
                    direction={orderBy === 'symbol' ? order : 'asc'}
                    onClick={() => handleRequestSort('symbol')}
                  >
                    Symbol
                  </TableSortLabel>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Company</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leSortLabel
                    active={orderBy === 'quantity'}
                    direction={orderBy === 'quantity' ? order : 'asc'}
                    onClick={() => handleRequestSort('quantity')}
                  >
                    Quantity
                  </TableSortLabel>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Avg Cost</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Current Price</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leSortLabel
                    active={orderBy === 'marketValue'}
                    direction={orderBy === 'marketValue' ? order : 'asc'}
                    onClick={() => handleRequestSort('marketValue')}
                  >
                    Market Value
                  </TableSortLabel>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leSortLabel
                    active={orderBy === 'gainLoss'}
                    direction={orderBy === 'gainLoss' ? order : 'asc'}
                    onClick={() => handleRequestSort('gainLoss')}
                  >
                    Gain/Loss
                  </TableSortLabel>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">% Change</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sector</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
              </tr>
            </thead>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
              {paginatedHoldings.map((holding) => (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={holding.id || holding.symbol}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                    <div  variant="body2" fontWeight="bold">
                      {holding.symbol}
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                    <div  variant="body2">
                      {holding.companyName || 'N/A'}
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{holding.quantity}</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    ${(holding.costBasis || 0).toFixed(2)}
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    ${(holding.currentPrice || 0).toFixed(2)}
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    ${(holding.marketValue || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                    align="right"
                    sx={{ color: (holding.gainLoss || 0) >= 0 ? 'success.main' : 'error.main' }}
                  >
                    ${(holding.gainLoss || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                    align="right"
                    sx={{ color: (holding.gainLossPercent || 0) >= 0 ? 'success.main' : 'error.main' }}
                  >
                    {(holding.gainLossPercent || 0) >= 0 ? '+' : ''}
                    {(holding.gainLossPercent || 0).toFixed(2)}%
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      label={holding.sector || 'Unknown'} 
                      size="small"
                      sx={{ 
                        backgroundColor: getSectorColor(holding.sector) + '20',
                        color: getSectorColor(holding.sector)
                      }}
                    />
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                    <button className="p-2 rounded-full hover:bg-gray-100"
                      size="small"
                      onClick={() => {
                        setSelectedHolding(holding);
                        setEditDialogOpen(true);
                      }}
                    >
                      <Edit />
                    </button>
                    <button className="p-2 rounded-full hover:bg-gray-100"
                      size="small"
                      color="error"
                      onClick={() => handleDeleteHolding(holding.id)}
                    >
                      <Delete />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"lePagination
          rowsPerPageOptions={[5, 10, 25, 50]}
          component="div"
          count={filteredHoldings.length}
          rowsPerPage={rowsPerPage}
          page={page}
          onPageChange={(event, newPage) => setPage(newPage)}
          onRowsPerPageChange={(event) => {
            setRowsPerPage(parseInt(event.target.value, 10));
            setPage(0);
          }}
        />
      </div>

      {/* Add Holding Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Add New Holding</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div  sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              label="Symbol"
              value={newHolding.symbol}
              onChange={(e) => setNewHolding({ ...newHolding, symbol: e.target.value.toUpperCase() })}
              required
            />
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              label="Quantity"
              type="number"
              value={newHolding.quantity}
              onChange={(e) => setNewHolding({ ...newHolding, quantity: e.target.value })}
              required
            />
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              label="Cost Basis (per share)"
              type="number"
              step="0.01"
              value={newHolding.costBasis}
              onChange={(e) => setNewHolding({ ...newHolding, costBasis: e.target.value })}
              required
            />
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              label="Purchase Date"
              type="date"
              value={newHolding.purchaseDate}
              onChange={(e) => setNewHolding({ ...newHolding, purchaseDate: e.target.value })}
              InputLabelProps={{ shrink: true }}
            />
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setAddDialogOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleAddHolding} variant="contained">Add Holding</button>
        </div>
      </div>

      {/* Edit Holding Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Edit Holding</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          {selectedHolding && (
            <div  sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Symbol"
                value={selectedHolding.symbol}
                disabled
              />
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Quantity"
                type="number"
                value={selectedHolding.quantity}
                onChange={(e) => setSelectedHolding({ ...selectedHolding, quantity: e.target.value })}
              />
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Cost Basis (per share)"
                type="number"
                step="0.01"
                value={selectedHolding.costBasis}
                onChange={(e) => setSelectedHolding({ ...selectedHolding, costBasis: e.target.value })}
              />
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Purchase Date"
                type="date"
                value={selectedHolding.purchaseDate}
                onChange={(e) => setSelectedHolding({ ...selectedHolding, purchaseDate: e.target.value })}
                InputLabelProps={{ shrink: true }}
              />
            </div>
          )}
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setEditDialogOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleEditHolding} variant="contained">Save Changes</button>
        </div>
      </div>

      {/* Import Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={importDialogOpen} onClose={() => setImportDialogOpen(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Import Portfolio</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div  variant="body2" sx={{ mb: 2 }}>
            Import your portfolio from a supported broker:
          </div>
          <div  sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              onClick={() => handleImportFromBroker('alpaca')}
              disabled={loading}
            >
              Import from Alpaca
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              onClick={() => handleImportFromBroker('robinhood')}
              disabled={loading}
            >
              Import from Robinhood
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              onClick={() => handleImportFromBroker('fidelity')}
              disabled={loading}
            >
              Import from Fidelity
            </button>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setImportDialogOpen(false)}>Cancel</button>
        </div>
      </div>
    </div>
  );
};

export default PortfolioHoldings;