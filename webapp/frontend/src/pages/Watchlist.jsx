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
  Assessment
} from '@mui/icons-material';
import { api } from '../services/api';
import { formatCurrency, formatPercentage } from '../utils/formatters';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';

function TabPanel({ children, value, index }) {
  return (
    <div hidden={value !== index}>
      {value === index && <Box sx={{ py: 2 }}>{children}</Box>}
    </div>
  );
}

const Watchlist = () => {
  const theme = useTheme();
  const [watchlists, setWatchlists] = useState([]);
  const [activeWatchlist, setActiveWatchlist] = useState(0);
  const [stocks, setStocks] = useState([]);
  const [allStocks, setAllStocks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedStock, setSelectedStock] = useState(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });
  const [anchorEl, setAnchorEl] = useState(null);
  const [newWatchlistName, setNewWatchlistName] = useState('');
  const [alerts, setAlerts] = useState({});
  const [refreshInterval, setRefreshInterval] = useState(null);

  // Default watchlists
  useEffect(() => {
    // Initialize with default watchlists
    const defaultWatchlists = [
      { id: 1, name: 'My Portfolio', stocks: [], editable: true },
      { id: 2, name: 'Tech Stocks', stocks: [], editable: true },
      { id: 3, name: 'Dividend Stocks', stocks: [], editable: true },
      { id: 4, name: 'Growth Stocks', stocks: [], editable: true }
    ];
    
    // Load from localStorage or use defaults
    const savedWatchlists = localStorage.getItem('watchlists');
    if (savedWatchlists) {
      setWatchlists(JSON.parse(savedWatchlists));
    } else {
      setWatchlists(defaultWatchlists);
    }

    loadAllStocks();
    loadWatchlistData();
  }, []);

  // Auto-refresh every 30 seconds when market is open
  useEffect(() => {
    const interval = setInterval(() => {
      if (isMarketOpen()) {
        loadWatchlistData();
      }
    }, 30000);
    
    setRefreshInterval(interval);
    return () => clearInterval(interval);
  }, [activeWatchlist]);

  const isMarketOpen = () => {
    const now = new Date();
    const day = now.getDay();
    const hour = now.getHours();
    const minute = now.getMinutes();
    const time = hour * 60 + minute;
    
    // Market hours: 9:30 AM - 4:00 PM ET (assuming EST/EDT)
    return day >= 1 && day <= 5 && time >= 570 && time < 960;
  };

  const loadAllStocks = async () => {
    try {
      const response = await api.get('/stocks/symbols');
      setAllStocks(response.data.symbols || []);
    } catch (error) {
      console.error('Error loading stock symbols:', error);
    }
  };

  const loadWatchlistData = async () => {
    if (watchlists.length === 0 || !watchlists[activeWatchlist]) return;
    
    setLoading(true);
    try {
      const symbols = watchlists[activeWatchlist].stocks;
      if (symbols.length === 0) {
        setStocks([]);
        return;
      }

      // Load market data for watchlist stocks
      const promises = symbols.map(symbol => 
        api.get(`/market-data/${symbol}`).catch(err => ({ error: true, symbol }))
      );
      
      const responses = await Promise.all(promises);
      const stockData = responses
        .filter(res => !res.error)
        .map(res => res.data);
      
      setStocks(stockData);
    } catch (error) {
      console.error('Error loading watchlist data:', error);
      setSnackbar({ open: true, message: 'Error loading watchlist data', severity: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleAddStock = async (symbol) => {
    if (!symbol) return;
    
    const updatedWatchlists = [...watchlists];
    const currentList = updatedWatchlists[activeWatchlist];
    
    if (currentList.stocks.includes(symbol)) {
      setSnackbar({ open: true, message: 'Stock already in watchlist', severity: 'warning' });
      return;
    }
    
    currentList.stocks.push(symbol);
    setWatchlists(updatedWatchlists);
    localStorage.setItem('watchlists', JSON.stringify(updatedWatchlists));
    
    // Load data for new stock
    try {
      const response = await api.get(`/market-data/${symbol}`);
      setStocks([...stocks, response.data]);
      setSnackbar({ open: true, message: `${symbol} added to watchlist`, severity: 'success' });
    } catch (error) {
      console.error('Error adding stock:', error);
      setSnackbar({ open: true, message: 'Error adding stock', severity: 'error' });
    }
  };

  const handleRemoveStock = (symbol) => {
    const updatedWatchlists = [...watchlists];
    const currentList = updatedWatchlists[activeWatchlist];
    
    currentList.stocks = currentList.stocks.filter(s => s !== symbol);
    setWatchlists(updatedWatchlists);
    localStorage.setItem('watchlists', JSON.stringify(updatedWatchlists));
    
    setStocks(stocks.filter(s => s.ticker !== symbol));
    setSnackbar({ open: true, message: `${symbol} removed from watchlist`, severity: 'success' });
  };

  const handleCreateWatchlist = () => {
    if (!newWatchlistName.trim()) return;
    
    const newId = Math.max(...watchlists.map(w => w.id)) + 1;
    const newWatchlist = {
      id: newId,
      name: newWatchlistName,
      stocks: [],
      editable: true
    };
    
    const updatedWatchlists = [...watchlists, newWatchlist];
    setWatchlists(updatedWatchlists);
    localStorage.setItem('watchlists', JSON.stringify(updatedWatchlists));
    
    setActiveWatchlist(watchlists.length);
    setNewWatchlistName('');
    setCreateDialogOpen(false);
    setSnackbar({ open: true, message: 'Watchlist created', severity: 'success' });
  };

  const handleDeleteWatchlist = () => {
    if (watchlists.length <= 1) {
      setSnackbar({ open: true, message: 'Cannot delete last watchlist', severity: 'error' });
      return;
    }
    
    const updatedWatchlists = watchlists.filter((_, index) => index !== activeWatchlist);
    setWatchlists(updatedWatchlists);
    localStorage.setItem('watchlists', JSON.stringify(updatedWatchlists));
    
    setActiveWatchlist(0);
    setAnchorEl(null);
    loadWatchlistData();
    setSnackbar({ open: true, message: 'Watchlist deleted', severity: 'success' });
  };

  const handleDragEnd = (result) => {
    if (!result.destination) return;
    
    const items = Array.from(stocks);
    const [reorderedItem] = items.splice(result.source.index, 1);
    items.splice(result.destination.index, 0, reorderedItem);
    
    setStocks(items);
    
    // Update watchlist order
    const updatedWatchlists = [...watchlists];
    updatedWatchlists[activeWatchlist].stocks = items.map(stock => stock.ticker);
    setWatchlists(updatedWatchlists);
    localStorage.setItem('watchlists', JSON.stringify(updatedWatchlists));
  };

  const handleSetAlert = (stock) => {
    setSelectedStock(stock);
    setAlertDialogOpen(true);
  };

  const handleSaveAlert = (alertConfig) => {
    const newAlerts = { ...alerts };
    newAlerts[selectedStock.ticker] = alertConfig;
    setAlerts(newAlerts);
    localStorage.setItem('watchlistAlerts', JSON.stringify(newAlerts));
    
    setAlertDialogOpen(false);
    setSnackbar({ open: true, message: 'Alert created', severity: 'success' });
  };

  const getChangeColor = (change) => {
    if (change > 0) return theme.palette.success.main;
    if (change < 0) return theme.palette.error.main;
    return theme.palette.text.secondary;
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Grid container spacing={3}>
        {/* Header */}
        <Grid item xs={12}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h4" fontWeight={700}>
              Watchlist
            </Typography>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Tooltip title="Refresh data">
                <IconButton onClick={loadWatchlistData} disabled={loading}>
                  <Refresh />
                </IconButton>
              </Tooltip>
              <Button
                variant="outlined"
                startIcon={<FilterList />}
                onClick={() => setEditMode(!editMode)}
              >
                {editMode ? 'Done' : 'Edit'}
              </Button>
              <Button
                variant="contained"
                startIcon={<Add />}
                onClick={() => setCreateDialogOpen(true)}
              >
                New Watchlist
              </Button>
            </Box>
          </Box>
        </Grid>

        {/* Watchlist Tabs */}
        <Grid item xs={12}>
          <Card>
            <CardContent sx={{ pb: 0 }}>
              <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                <Tabs 
                  value={activeWatchlist} 
                  onChange={(e, newValue) => {
                    setActiveWatchlist(newValue);
                    loadWatchlistData();
                  }}
                  variant="scrollable"
                  scrollButtons="auto"
                >
                  {watchlists.map((watchlist, index) => (
                    <Tab 
                      key={watchlist.id} 
                      label={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          {watchlist.name}
                          <Chip label={watchlist.stocks.length} size="small" />
                        </Box>
                      }
                    />
                  ))}
                </Tabs>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Add Stock */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Autocomplete
                options={allStocks}
                getOptionLabel={(option) => `${option.symbol} - ${option.name}`}
                renderInput={(params) => (
                  <TextField 
                    {...params} 
                    label="Add stock to watchlist" 
                    placeholder="Search by symbol or name"
                    InputProps={{
                      ...params.InputProps,
                      startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />
                    }}
                  />
                )}
                onChange={(event, value) => {
                  if (value) {
                    handleAddStock(value.symbol);
                  }
                }}
              />
            </CardContent>
          </Card>
        </Grid>

        {/* Watchlist Table */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              {loading ? (
                <LinearProgress />
              ) : stocks.length === 0 ? (
                <Alert severity="info">
                  No stocks in this watchlist. Add stocks using the search above.
                </Alert>
              ) : (
                <DragDropContext onDragEnd={handleDragEnd}>
                  <Droppable droppableId="watchlist">
                    {(provided) => (
                      <TableContainer 
                        component={Paper} 
                        variant="outlined"
                        {...provided.droppableProps}
                        ref={provided.innerRef}
                      >
                        <Table>
                          <TableHead>
                            <TableRow>
                              {editMode && <TableCell width={40} />}
                              <TableCell>Symbol</TableCell>
                              <TableCell>Company</TableCell>
                              <TableCell align="right">Price</TableCell>
                              <TableCell align="right">Change</TableCell>
                              <TableCell align="right">Change %</TableCell>
                              <TableCell align="right">Volume</TableCell>
                              <TableCell align="right">Market Cap</TableCell>
                              <TableCell align="center">Alerts</TableCell>
                              <TableCell align="center">Actions</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {stocks.map((stock, index) => (
                              <Draggable 
                                key={stock.ticker} 
                                draggableId={stock.ticker} 
                                index={index}
                                isDragDisabled={!editMode}
                              >
                                {(provided, snapshot) => (
                                  <TableRow
                                    ref={provided.innerRef}
                                    {...provided.draggableProps}
                                    style={{
                                      ...provided.draggableProps.style,
                                      backgroundColor: snapshot.isDragging 
                                        ? alpha(theme.palette.primary.main, 0.1) 
                                        : 'transparent'
                                    }}
                                    hover
                                  >
                                    {editMode && (
                                      <TableCell {...provided.dragHandleProps}>
                                        <DragIndicator sx={{ cursor: 'grab' }} />
                                      </TableCell>
                                    )}
                                    <TableCell>
                                      <Typography variant="subtitle2" fontWeight={600}>
                                        {stock.ticker}
                                      </Typography>
                                    </TableCell>
                                    <TableCell>
                                      <Typography variant="body2" noWrap sx={{ maxWidth: 200 }}>
                                        {stock.name}
                                      </Typography>
                                    </TableCell>
                                    <TableCell align="right">
                                      <Typography variant="body2" fontWeight={600}>
                                        {formatCurrency(stock.current_price)}
                                      </Typography>
                                    </TableCell>
                                    <TableCell align="right">
                                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                                        {stock.change_amount > 0 ? (
                                          <ArrowUpward sx={{ fontSize: 16, color: getChangeColor(stock.change_amount) }} />
                                        ) : (
                                          <ArrowDownward sx={{ fontSize: 16, color: getChangeColor(stock.change_amount) }} />
                                        )}
                                        <Typography 
                                          variant="body2" 
                                          sx={{ color: getChangeColor(stock.change_amount) }}
                                        >
                                          {formatCurrency(Math.abs(stock.change_amount))}
                                        </Typography>
                                      </Box>
                                    </TableCell>
                                    <TableCell align="right">
                                      <Chip
                                        label={`${stock.change_percent >= 0 ? '+' : ''}${stock.change_percent.toFixed(2)}%`}
                                        size="small"
                                        sx={{
                                          backgroundColor: alpha(getChangeColor(stock.change_percent), 0.1),
                                          color: getChangeColor(stock.change_percent),
                                          fontWeight: 600
                                        }}
                                      />
                                    </TableCell>
                                    <TableCell align="right">
                                      <Typography variant="body2">
                                        {(stock.volume / 1000000).toFixed(2)}M
                                      </Typography>
                                    </TableCell>
                                    <TableCell align="right">
                                      <Typography variant="body2">
                                        {formatCurrency(stock.market_cap / 1000000000)}B
                                      </Typography>
                                    </TableCell>
                                    <TableCell align="center">
                                      <IconButton 
                                        size="small"
                                        onClick={() => handleSetAlert(stock)}
                                        color={alerts[stock.ticker] ? 'primary' : 'default'}
                                      >
                                        {alerts[stock.ticker] ? <NotificationsActive /> : <Notifications />}
                                      </IconButton>
                                    </TableCell>
                                    <TableCell align="center">
                                      <Stack direction="row" spacing={1} justifyContent="center">
                                        <Tooltip title="View details">
                                          <IconButton 
                                            size="small"
                                            onClick={() => window.location.href = `/stocks/${stock.ticker}`}
                                          >
                                            <ShowChart />
                                          </IconButton>
                                        </Tooltip>
                                        {editMode && (
                                          <Tooltip title="Remove from watchlist">
                                            <IconButton 
                                              size="small" 
                                              color="error"
                                              onClick={() => handleRemoveStock(stock.ticker)}
                                            >
                                              <Delete />
                                            </IconButton>
                                          </Tooltip>
                                        )}
                                      </Stack>
                                    </TableCell>
                                  </TableRow>
                                )}
                              </Draggable>
                            ))}
                            {provided.placeholder}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    )}
                  </Droppable>
                </DragDropContext>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Summary Stats */}
        <Grid item xs={12}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                    Total Value
                  </Typography>
                  <Typography variant="h5" fontWeight={600}>
                    {formatCurrency(stocks.reduce((sum, stock) => sum + stock.current_price, 0))}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                    Day's Change
                  </Typography>
                  <Typography 
                    variant="h5" 
                    fontWeight={600}
                    color={stocks.reduce((sum, stock) => sum + stock.change_amount, 0) >= 0 ? 'success.main' : 'error.main'}
                  >
                    {formatCurrency(stocks.reduce((sum, stock) => sum + stock.change_amount, 0))}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                    Winners
                  </Typography>
                  <Typography variant="h5" fontWeight={600} color="success.main">
                    {stocks.filter(s => s.change_percent > 0).length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                    Losers
                  </Typography>
                  <Typography variant="h5" fontWeight={600} color="error.main">
                    {stocks.filter(s => s.change_percent < 0).length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
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
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                handleCreateWatchlist();
              }
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleCreateWatchlist} variant="contained">Create</Button>
        </DialogActions>
      </Dialog>

      {/* Alert Dialog */}
      <Dialog 
        open={alertDialogOpen} 
        onClose={() => setAlertDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Set Price Alert for {selectedStock?.ticker}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Alert Type</InputLabel>
                <Select defaultValue="price_above">
                  <MenuItem value="price_above">Price Above</MenuItem>
                  <MenuItem value="price_below">Price Below</MenuItem>
                  <MenuItem value="percent_change">Percent Change</MenuItem>
                  <MenuItem value="volume_surge">Volume Surge</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Alert Value"
                type="number"
                defaultValue={selectedStock?.current_price}
                InputProps={{
                  startAdornment: <AttachMoney />
                }}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={<Switch defaultChecked />}
                label="Email notifications"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAlertDialogOpen(false)}>Cancel</Button>
          <Button onClick={() => handleSaveAlert({})} variant="contained">Save Alert</Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={3000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
        message={snackbar.message}
      />
    </Container>
  );
};

export default Watchlist;