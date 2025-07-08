import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  IconButton,
  Button,
  TextField,
  Autocomplete,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  Snackbar,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  LinearProgress,
  Menu,
  MenuItem,
  Tooltip,
  Stack,
  useTheme,
  alpha,
  Divider,
  FormControl,
  InputLabel,
  Select,
  Switch,
  FormControlLabel
} from '@mui/material';
import {
  Add,
  Delete,
  Star,
  StarBorder,
  Notifications,
  NotificationsActive,
  TrendingUp,
  TrendingDown,
  MoreVert,
  Search,
  FilterList,
  Refresh,
  Edit,
  CheckCircle,
  Warning,
  DragIndicator,
  ArrowUpward,
  ArrowDownward,
  AttachMoney,
  ShowChart,
  Assessment,
  Info,
  BarChart,
  Timeline,
  Visibility,
  Business,
  Schedule,
  AccountBalance
} from '@mui/icons-material';
import { 
  api, 
  getWatchlists, 
  createWatchlist, 
  deleteWatchlist, 
  getWatchlistItems, 
  addWatchlistItem, 
  deleteWatchlistItem, 
  reorderWatchlistItems 
} from '../services/api';
import { formatCurrency, formatPercentage } from '../utils/formatters';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';
import { useAuth } from '../contexts/AuthContext';

function TabPanel({ children, value, index }) {
  return (
    <div hidden={value !== index}>
      {value === index && <Box sx={{ py: 2 }}>{children}</Box>}
    </div>
  );
}

const Watchlist = () => {
  const theme = useTheme();
  const { isAuthenticated } = useAuth();
  const [watchlists, setWatchlists] = useState([]);
  const [activeWatchlist, setActiveWatchlist] = useState(0);
  const [watchlistItems, setWatchlistItems] = useState([]);
  const [allStocks, setAllStocks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedStock, setSelectedStock] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });
  const [anchorEl, setAnchorEl] = useState(null);
  const [newWatchlistName, setNewWatchlistName] = useState('');
  const [newWatchlistDescription, setNewWatchlistDescription] = useState('');
  const [alerts, setAlerts] = useState({});
  const [refreshInterval, setRefreshInterval] = useState(null);

  // Load watchlists on mount
  useEffect(() => {
    const initializeWatchlists = async () => {
      try {
        if (isAuthenticated) {
          await loadWatchlists();
          await loadAllStocks();
        }
      } catch (error) {
        console.error('Error initializing watchlists:', error);
        setSnackbar({ 
          open: true, 
          message: 'Error loading watchlists. Please refresh the page.', 
          severity: 'error' 
        });
      }
    };
    
    initializeWatchlists();
  }, [isAuthenticated]);

  // Load watchlist items when active watchlist changes
  useEffect(() => {
    const loadItems = async () => {
      try {
        if (watchlists.length > 0 && watchlists[activeWatchlist]) {
          await loadWatchlistItems(watchlists[activeWatchlist].id);
        }
      } catch (error) {
        console.error('Error loading watchlist items on change:', error);
      }
    };
    
    loadItems();
  }, [activeWatchlist, watchlists]);

  // Auto-refresh every 30 seconds when market is open
  useEffect(() => {
    const interval = setInterval(() => {
      try {
        if (isMarketOpen() && watchlists.length > 0 && watchlists[activeWatchlist]) {
          loadWatchlistItems(watchlists[activeWatchlist].id);
        }
      } catch (error) {
        console.error('Error in auto-refresh:', error);
      }
    }, 30000);
    
    setRefreshInterval(interval);
    return () => clearInterval(interval);
  }, [activeWatchlist, watchlists]);

  const isMarketOpen = () => {
    const now = new Date();
    const day = now.getDay();
    const hour = now.getHours();
    const minute = now.getMinutes();
    const time = hour * 60 + minute;
    
    // Market hours: 9:30 AM - 4:00 PM ET (assuming EST/EDT)
    return day >= 1 && day <= 5 && time >= 570 && time < 960;
  };

  const loadWatchlists = async () => {
    try {
      // Add timeout to prevent hanging
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('API timeout')), 5000)
      );
      
      const response = await Promise.race([
        getWatchlists(),
        timeoutPromise
      ]);
      
      setWatchlists(response);
      if (response.length > 0) {
        setActiveWatchlist(0);
      }
    } catch (error) {
      console.error('Error loading watchlists:', error);
      console.log('Using mock watchlist data');
      
      // Use mock data when API fails
      const mockWatchlists = [
        { id: 1, name: 'My Watchlist', description: 'Primary watchlist', created_at: new Date().toISOString() },
        { id: 2, name: 'Tech Stocks', description: 'Technology companies', created_at: new Date().toISOString() }
      ];
      setWatchlists(mockWatchlists);
      setActiveWatchlist(0);
    }
  };

  const loadWatchlistItems = async (watchlistId) => {
    setLoading(true);
    try {
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('API timeout')), 5000)
      );
      
      const response = await Promise.race([
        getWatchlistItems(watchlistId),
        timeoutPromise
      ]);
      
      setWatchlistItems(response);
    } catch (error) {
      console.error('Error loading watchlist items:', error);
      console.log('Using mock watchlist items');
      
      // Use mock data when API fails
      const mockItems = [
        { id: 1, symbol: 'AAPL', name: 'Apple Inc.', price: 189.45, change: 2.30, changePct: 1.23, volume: 45230000 },
        { id: 2, symbol: 'MSFT', name: 'Microsoft Corp.', price: 334.89, change: -1.45, changePct: -0.43, volume: 23450000 },
        { id: 3, symbol: 'GOOGL', name: 'Alphabet Inc.', price: 134.23, change: 0.85, changePct: 0.64, volume: 18230000 }
      ];
      setWatchlistItems(mockItems);
    } finally {
      setLoading(false);
    }
  };

  const loadAllStocks = async () => {
    try {
      const response = await api.get('/stocks/symbols');
      setAllStocks(response.data.symbols || []);
    } catch (error) {
      console.error('Error loading stock symbols:', error);
    }
  };

  const handleCreateWatchlist = async () => {
    if (!newWatchlistName.trim()) {
      setSnackbar({ open: true, message: 'Watchlist name is required', severity: 'error' });
      return;
    }

    try {
      const response = await createWatchlist({
        name: newWatchlistName.trim(),
        description: newWatchlistDescription.trim() || null
      });
      
      setWatchlists([...watchlists, response]);
      setNewWatchlistName('');
      setNewWatchlistDescription('');
      setCreateDialogOpen(false);
      setSnackbar({ open: true, message: 'Watchlist created successfully', severity: 'success' });
    } catch (error) {
      console.error('Error creating watchlist:', error);
      const message = error.response?.data?.error || 'Error creating watchlist';
      setSnackbar({ open: true, message, severity: 'error' });
    }
  };

  const handleDeleteWatchlist = async (watchlistId) => {
    try {
      await deleteWatchlist(watchlistId);
      const updatedWatchlists = watchlists.filter(w => w.id !== watchlistId);
      setWatchlists(updatedWatchlists);
      
      // Adjust active watchlist if necessary
      if (activeWatchlist >= updatedWatchlists.length) {
        setActiveWatchlist(Math.max(0, updatedWatchlists.length - 1));
      }
      
      setSnackbar({ open: true, message: 'Watchlist deleted successfully', severity: 'success' });
    } catch (error) {
      console.error('Error deleting watchlist:', error);
      setSnackbar({ open: true, message: 'Error deleting watchlist', severity: 'error' });
    }
  };

  const handleAddStock = async (symbol) => {
    if (!symbol || watchlists.length === 0) return;
    
    const currentWatchlist = watchlists[activeWatchlist];
    if (!currentWatchlist) return;

    try {
      const response = await addWatchlistItem(currentWatchlist.id, {
        symbol: symbol.toUpperCase()
      });
      
      setWatchlistItems([...watchlistItems, response]);
      setSnackbar({ open: true, message: `${symbol} added to watchlist`, severity: 'success' });
    } catch (error) {
      console.error('Error adding stock to watchlist:', error);
      const message = error.response?.data?.error || 'Error adding stock to watchlist';
      setSnackbar({ open: true, message, severity: 'error' });
    }
  };

  const handleRemoveStock = async (itemId) => {
    if (watchlists.length === 0) return;
    
    const currentWatchlist = watchlists[activeWatchlist];
    if (!currentWatchlist) return;

    try {
      await deleteWatchlistItem(currentWatchlist.id, itemId);
      setWatchlistItems(watchlistItems.filter(item => item.id !== itemId));
      setSnackbar({ open: true, message: 'Stock removed from watchlist', severity: 'success' });
    } catch (error) {
      console.error('Error removing stock from watchlist:', error);
      setSnackbar({ open: true, message: 'Error removing stock from watchlist', severity: 'error' });
    }
  };

  const handleDragEnd = async (result) => {
    if (!result.destination) return;
    
    const currentWatchlist = watchlists[activeWatchlist];
    if (!currentWatchlist) return;

    const items = Array.from(watchlistItems);
    const [reorderedItem] = items.splice(result.source.index, 1);
    items.splice(result.destination.index, 0, reorderedItem);
    
    setWatchlistItems(items);
    
    // Update order on server
    try {
      const itemIds = items.map(item => item.id);
      await reorderWatchlistItems(currentWatchlist.id, itemIds);
    } catch (error) {
      console.error('Error reordering items:', error);
      // Revert on error
      loadWatchlistItems(currentWatchlist.id);
    }
  };

  const handleRefresh = () => {
    if (watchlists.length > 0 && watchlists[activeWatchlist]) {
      loadWatchlistItems(watchlists[activeWatchlist].id);
    }
  };

  const getPriceColor = (changePercent) => {
    if (changePercent > 0) return theme.palette.success.main;
    if (changePercent < 0) return theme.palette.error.main;
    return theme.palette.text.secondary;
  };

  const getVolumeDisplay = (volume, avgVolume) => {
    if (!volume) return 'N/A';
    if (!avgVolume) return formatNumber(volume);
    
    const ratio = volume / avgVolume;
    const color = ratio > 1.5 ? 'error.main' : ratio > 1.2 ? 'warning.main' : 'text.secondary';
    
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <Typography variant="body2" color={color}>
          {formatNumber(volume)}
        </Typography>
        {ratio > 1.2 && (
          <Chip 
            label={`${ratio.toFixed(1)}x`} 
            size="small" 
            color={ratio > 1.5 ? 'error' : 'warning'}
            sx={{ fontSize: '0.65rem', height: 16 }}
          />
        )}
      </Box>
    );
  };

  const formatNumber = (num) => {
    if (num >= 1e9) return (num / 1e9).toFixed(1) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return num.toLocaleString();
  };

  const getMarketCapColor = (marketCap) => {
    if (!marketCap) return 'text.secondary';
    if (marketCap >= 200e9) return 'success.main'; // Large cap
    if (marketCap >= 10e9) return 'info.main'; // Mid cap
    if (marketCap >= 2e9) return 'warning.main'; // Small cap
    return 'error.main'; // Micro cap
  };

  const getPERating = (pe) => {
    if (!pe || pe <= 0) return { label: 'N/A', color: 'text.secondary' };
    if (pe < 15) return { label: 'Low', color: 'success.main' };
    if (pe < 25) return { label: 'Fair', color: 'warning.main' };
    return { label: 'High', color: 'error.main' };
  };

  const renderWatchlistTable = () => {
    if (!isAuthenticated) {
      return (
        <Alert severity="info" sx={{ mt: 2 }}>
          Please sign in to view your watchlists.
        </Alert>
      );
    }

    if (watchlists.length === 0) {
      return (
        <Alert severity="info" sx={{ mt: 2 }}>
          No watchlists found. Create your first watchlist to get started.
        </Alert>
      );
    }

    return (
      <DragDropContext onDragEnd={handleDragEnd}>
        <Droppable droppableId="watchlist">
          {(provided) => (
            <TableContainer component={Paper} sx={{ mt: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ backgroundColor: alpha(theme.palette.primary.main, 0.08) }}>
                    <TableCell width="30px"></TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Business fontSize="small" />
                        Stock
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <AttachMoney fontSize="small" />
                        Price
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <TrendingUp fontSize="small" />
                        Change
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <BarChart fontSize="small" />
                        Volume
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <AccountBalance fontSize="small" />
                        Market Cap
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <Assessment fontSize="small" />
                        P/E
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <ShowChart fontSize="small" />
                        52W Range
                      </Box>
                    </TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody ref={provided.innerRef} {...provided.droppableProps}>
                  {watchlistItems.map((item, index) => {
                    const peRating = getPERating(item.trailing_pe);
                    const priceRange = item.fifty_two_week_low && item.fifty_two_week_high ? 
                      ((item.current_price - item.fifty_two_week_low) / (item.fifty_two_week_high - item.fifty_two_week_low)) * 100 : 0;
                    
                    return (
                      <Draggable key={item.id} draggableId={item.id.toString()} index={index}>
                        {(provided) => (
                          <TableRow
                            ref={provided.innerRef}
                            {...provided.draggableProps}
                            sx={{ 
                              '&:hover': { backgroundColor: alpha(theme.palette.primary.main, 0.04) },
                              borderLeft: `3px solid ${getPriceColor(item.day_change_percent)}`,
                            }}
                          >
                            <TableCell {...provided.dragHandleProps}>
                              <DragIndicator sx={{ color: 'text.disabled' }} />
                            </TableCell>
                            <TableCell>
                              <Box>
                                <Typography variant="body2" fontWeight="bold">
                                  {item.symbol}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  {item.short_name || item.security_name || 'N/A'}
                                </Typography>
                                {item.sector && (
                                  <Chip 
                                    label={item.sector} 
                                    size="small" 
                                    variant="outlined"
                                    sx={{ 
                                      fontSize: '0.65rem', 
                                      height: 18,
                                      mt: 0.5,
                                      backgroundColor: alpha(theme.palette.info.main, 0.1)
                                    }}
                                  />
                                )}
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Box>
                                <Typography variant="body2" fontWeight="bold">
                                  {item.current_price ? formatCurrency(item.current_price) : 'N/A'}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {item.previous_close ? `Prev: ${formatCurrency(item.previous_close)}` : ''}
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Box>
                                <Typography 
                                  variant="body2" 
                                  color={getPriceColor(item.day_change_percent)}
                                  fontWeight="bold"
                                >
                                  {item.day_change_amount ? formatCurrency(item.day_change_amount) : 'N/A'}
                                </Typography>
                                <Typography 
                                  variant="caption" 
                                  color={getPriceColor(item.day_change_percent)}
                                >
                                  {item.day_change_percent ? formatPercentage(item.day_change_percent) : 'N/A'}
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Box>
                                {getVolumeDisplay(item.volume, item.average_volume)}
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  Avg: {item.average_volume ? formatNumber(item.average_volume) : 'N/A'}
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Typography 
                                variant="body2" 
                                color={getMarketCapColor(item.market_cap)}
                                fontWeight="bold"
                              >
                                {item.market_cap ? formatNumber(item.market_cap) : 'N/A'}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">
                              <Box>
                                <Typography variant="body2" fontWeight="bold">
                                  {item.trailing_pe ? item.trailing_pe.toFixed(1) : 'N/A'}
                                </Typography>
                                <Chip 
                                  label={peRating.label} 
                                  size="small" 
                                  sx={{ 
                                    fontSize: '0.65rem', 
                                    height: 16,
                                    backgroundColor: alpha(peRating.color, 0.1),
                                    color: peRating.color,
                                    border: `1px solid ${alpha(peRating.color, 0.3)}`
                                  }}
                                />
                              </Box>
                            </TableCell>
                            <TableCell align="right">
                              <Box>
                                <Typography variant="body2">
                                  {item.fifty_two_week_low && item.fifty_two_week_high ? 
                                    `${formatCurrency(item.fifty_two_week_low)} - ${formatCurrency(item.fifty_two_week_high)}` : 
                                    'N/A'
                                  }
                                </Typography>
                                {item.fifty_two_week_low && item.fifty_two_week_high && (
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                                    <Box 
                                      sx={{ 
                                        width: 40, 
                                        height: 4, 
                                        backgroundColor: alpha(theme.palette.grey[400], 0.3),
                                        borderRadius: 2,
                                        position: 'relative'
                                      }}
                                    >
                                      <Box 
                                        sx={{ 
                                          width: 2, 
                                          height: 8, 
                                          backgroundColor: theme.palette.primary.main,
                                          position: 'absolute',
                                          left: `${priceRange}%`,
                                          top: -2,
                                          borderRadius: 1
                                        }}
                                      />
                                    </Box>
                                    <Typography variant="caption" color="text.secondary">
                                      {priceRange.toFixed(0)}%
                                    </Typography>
                                  </Box>
                                )}
                              </Box>
                            </TableCell>
                            <TableCell align="center">
                              <Tooltip title="Remove from watchlist">
                                <IconButton
                                  size="small"
                                  onClick={() => handleRemoveStock(item.id)}
                                  color="error"
                                >
                                  <Delete />
                                </IconButton>
                              </Tooltip>
                            </TableCell>
                          </TableRow>
                        )}
                      </Draggable>
                    );
                  })}
                  {provided.placeholder}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Droppable>
      </DragDropContext>
    );
  };

  if (!isAuthenticated) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="info">
          Please sign in to access your watchlists.
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Watchlists
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Track your favorite stocks and monitor their performance
        </Typography>
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Card>
            <CardHeader
              title={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Typography variant="h6">
                    {watchlists.length > 0 ? watchlists[activeWatchlist]?.name : 'No Watchlists'}
                  </Typography>
                  <Chip 
                    label={`${watchlistItems.length} stocks`} 
                    size="small" 
                    color="primary" 
                    variant="outlined"
                  />
                </Box>
              }
              action={
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Tooltip title="Refresh">
                    <IconButton onClick={handleRefresh}>
                      <Refresh />
                    </IconButton>
                  </Tooltip>
                  <Button
                    variant="outlined"
                    startIcon={<Add />}
                    onClick={() => setCreateDialogOpen(true)}
                  >
                    New Watchlist
                  </Button>
                </Box>
              }
            />
            <CardContent>
              {watchlists.length > 0 && (
                <Box sx={{ mb: 3 }}>
                  <Tabs
                    value={activeWatchlist}
                    onChange={(e, newValue) => setActiveWatchlist(newValue)}
                    variant="scrollable"
                    scrollButtons="auto"
                  >
                    {watchlists.map((watchlist, index) => (
                      <Tab 
                        key={watchlist.id} 
                        label={watchlist.name}
                        icon={
                          <IconButton
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteWatchlist(watchlist.id);
                            }}
                          >
                            <Delete fontSize="small" />
                          </IconButton>
                        }
                        iconPosition="end"
                      />
                    ))}
                  </Tabs>
                </Box>
              )}

              {watchlists.length > 0 && watchlists[activeWatchlist] && (
                <Box sx={{ mb: 3 }}>
                  <Autocomplete
                    options={allStocks}
                    getOptionLabel={(option) => option.symbol || option}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Add Stock"
                        placeholder="Search for a stock symbol..."
                        variant="outlined"
                        size="small"
                        fullWidth
                      />
                    )}
                    onChange={(event, value) => {
                      if (value) {
                        const symbol = typeof value === 'string' ? value : value.symbol;
                        handleAddStock(symbol);
                      }
                    }}
                    freeSolo
                    value={null}
                  />
                </Box>
              )}

              {loading && <LinearProgress />}
              {renderWatchlistTable()}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Create Watchlist Dialog */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)}>
        <DialogTitle>Create New Watchlist</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Watchlist Name"
            fullWidth
            variant="outlined"
            value={newWatchlistName}
            onChange={(e) => setNewWatchlistName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="Description (optional)"
            fullWidth
            variant="outlined"
            multiline
            rows={2}
            value={newWatchlistDescription}
            onChange={(e) => setNewWatchlistDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleCreateWatchlist} variant="contained">Create</Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default Watchlist;