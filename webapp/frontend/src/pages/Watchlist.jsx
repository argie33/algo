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
      {value === index && <div  sx={{ py: 2 }}>{children}</div>}
    </div>
  );
}

const Watchlist = () => {
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
      
      // Ensure response is an array before setting state
      if (Array.isArray(response)) {
        setWatchlistItems(response);
      } else if (response && Array.isArray(response.data)) {
        setWatchlistItems(response.data);
      } else if (response && response.data && Array.isArray(response.data.items)) {
        setWatchlistItems(response.data.items);
      } else if (response && response.success && response.data) {
        // Handle case where data is an object with items or other structure
        console.log('API response structure:', response);
        if (Array.isArray(response.data.watchlistItems)) {
          setWatchlistItems(response.data.watchlistItems);
        } else if (Array.isArray(response.data.stocks)) {
          setWatchlistItems(response.data.stocks);
        } else {
          // If data is an object but no recognizable array, use empty array
          console.warn('No recognizable array in API response, using empty array');
          setWatchlistItems([]);
        }
      } else {
        console.warn('API response is not an array:', response);
        throw new Error('Invalid API response format');
      }
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
      
      // Handle specific error cases
      if (error.response?.status === 404) {
        // Item already deleted or doesn't exist - remove from local state
        setWatchlistItems(watchlistItems.filter(item => item.id !== itemId));
        setSnackbar({ 
          open: true, 
          message: 'Stock was already removed from watchlist', 
          severity: 'info' 
        });
      } else {
        // Other errors
        const errorMessage = error.response?.data?.error || 'Error removing stock from watchlist';
        setSnackbar({ 
          open: true, 
          message: errorMessage, 
          severity: 'error' 
        });
      }
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
    if (changePercent > 0) return '#4caf50';
    if (changePercent < 0) return '#f44336';
    return 'rgba(0, 0, 0, 0.6)';
  };

  const getVolumeDisplay = (volume, avgVolume) => {
    if (!volume) return 'N/A';
    if (!avgVolume) return formatNumber(volume);
    
    const ratio = volume / avgVolume;
    const color = ratio > 1.5 ? 'error.main' : ratio > 1.2 ? 'warning.main' : 'text.secondary';
    
    return (
      <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <div  variant="body2" color={color}>
          {formatNumber(volume)}
        </div>
        {ratio > 1.2 && (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
            label={`${ratio.toFixed(1)}x`} 
            size="small" 
            color={ratio > 1.5 ? 'error' : 'warning'}
            sx={{ fontSize: '0.65rem', height: 16 }}
          />
        )}
      </div>
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
    if (!pe || pe <= 0) return { label: 'N/A', color: '#666666' }; // Use hex color instead of theme color
    if (pe < 15) return { label: 'Low', color: '#4caf50' }; // success color
    if (pe < 25) return { label: 'Fair', color: '#ff9800' }; // warning color
    return { label: 'High', color: '#f44336' }; // error color
  };

  const renderWatchlistTable = () => {
    if (!isAuthenticated) {
      return (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mt: 2 }}>
          Please sign in to view your watchlists.
        </div>
      );
    }

    if (watchlists.length === 0) {
      return (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mt: 2 }}>
          No watchlists found. Create your first watchlist to get started.
        </div>
      );
    }

    return (
      <DragDropContext onDragEnd={handleDragEnd}>
        <Droppable droppableId="watchlist">
          {(provided) => (
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} sx={{ mt: 2 }}>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow sx={{ backgroundColor: '#1976d214' }}>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell width="30px"></td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Business fontSize="small" />
                        Stock
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <AttachMoney fontSize="small" />
                        Price
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <TrendingUp fontSize="small" />
                        Change
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <BarChart fontSize="small" />
                        Volume
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <AccountBalance fontSize="small" />
                        Market Cap
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <Assessment fontSize="small" />
                        P/E
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, justifyContent: 'flex-end' }}>
                        <ShowChart fontSize="small" />
                        52W Range
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody ref={provided.innerRef} {...provided.droppableProps}>
                  {(watchlistItems || []).map((item, index) => {
                    const peRating = getPERating(item.trailing_pe);
                    const priceRange = item.fifty_two_week_low && item.fifty_two_week_high ? 
                      ((item.current_price - item.fifty_two_week_low) / (item.fifty_two_week_high - item.fifty_two_week_low)) * 100 : 0;
                    
                    return (
                      <Draggable key={item.id} draggableId={item.id.toString()} index={index}>
                        {(provided) => (
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow
                            ref={provided.innerRef}
                            {...provided.draggableProps}
                            sx={{ 
                              '&:hover': { backgroundColor: '#1976d20A' },
                              borderLeft: `3px solid ${getPriceColor(item.day_change_percent)}`,
                            }}
                          >
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell {...provided.dragHandleProps}>
                              <DragIndicator sx={{ color: 'text.disabled' }} />
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                              <div>
                                <div  variant="body2" fontWeight="bold">
                                  {item.symbol}
                                </div>
                                <div  variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  {item.short_name || item.security_name || 'N/A'}
                                </div>
                                {item.sector && (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                    label={item.sector} 
                                    size="small" 
                                    variant="outlined"
                                    sx={{ 
                                      fontSize: '0.65rem', 
                                      height: 18,
                                      mt: 0.5,
                                      backgroundColor: '#2196f31A'
                                    }}
                                  />
                                )}
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div>
                                <div  variant="body2" fontWeight="bold">
                                  {item.current_price ? formatCurrency(item.current_price) : 'N/A'}
                                </div>
                                <div  variant="caption" color="text.secondary">
                                  {item.previous_close ? `Prev: ${formatCurrency(item.previous_close)}` : ''}
                                </div>
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div>
                                <div  
                                  variant="body2" 
                                  color={getPriceColor(item.day_change_percent)}
                                  fontWeight="bold"
                                >
                                  {item.day_change_amount ? formatCurrency(item.day_change_amount) : 'N/A'}
                                </div>
                                <div  
                                  variant="caption" 
                                  color={getPriceColor(item.day_change_percent)}
                                >
                                  {item.day_change_percent ? formatPercentage(item.day_change_percent) : 'N/A'}
                                </div>
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div>
                                {getVolumeDisplay(item.volume, item.average_volume)}
                                <div  variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                                  Avg: {item.average_volume ? formatNumber(item.average_volume) : 'N/A'}
                                </div>
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div  
                                variant="body2" 
                                color={getMarketCapColor(item.market_cap)}
                                fontWeight="bold"
                              >
                                {item.market_cap ? formatNumber(item.market_cap) : 'N/A'}
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div>
                                <div  variant="body2" fontWeight="bold">
                                  {item.trailing_pe ? item.trailing_pe.toFixed(1) : 'N/A'}
                                </div>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={peRating.label} 
                                  size="small" 
                                  sx={{ 
                                    fontSize: '0.65rem', 
                                    height: 16,
                                    backgroundColor: peRating.color + '1A',
                                    color: peRating.color,
                                    border: `1px solid ${peRating.color + '4D'}`
                                  }}
                                />
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div>
                                <div  variant="body2">
                                  {item.fifty_two_week_low && item.fifty_two_week_high ? 
                                    `${formatCurrency(item.fifty_two_week_low)} - ${formatCurrency(item.fifty_two_week_high)}` : 
                                    'N/A'
                                  }
                                </div>
                                {item.fifty_two_week_low && item.fifty_two_week_high && (
                                  <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                                    <div  
                                      sx={{ 
                                        width: 40, 
                                        height: 4, 
                                        backgroundColor: '#bdbdbd4D',
                                        borderRadius: 2,
                                        position: 'relative'
                                      }}
                                    >
                                      <div  
                                        sx={{ 
                                          width: 2, 
                                          height: 8, 
                                          backgroundColor: '#1976d2',
                                          position: 'absolute',
                                          left: `${priceRange}%`,
                                          top: -2,
                                          borderRadius: 1
                                        }}
                                      />
                                    </div>
                                    <div  variant="caption" color="text.secondary">
                                      {priceRange.toFixed(0)}%
                                    </div>
                                  </div>
                                )}
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                              <div  title="Remove from watchlist">
                                <button className="p-2 rounded-full hover:bg-gray-100"
                                  size="small"
                                  onClick={() => handleRemoveStock(item.id)}
                                  color="error"
                                >
                                  <Delete />
                                </button>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Draggable>
                    );
                  })}
                  {provided.placeholder}
                </tbody>
              </table>
            </div>
          )}
        </Droppable>
      </DragDropContext>
    );
  };

  if (!isAuthenticated) {
    return (
      <div className="container mx-auto" maxWidth="lg" sx={{ py: 4 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
          Please sign in to access your watchlists.
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="lg" sx={{ py: 4 }}>
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" component="h1" gutterBottom>
          Watchlists
        </div>
        <div  variant="body1" color="text.secondary">
          Track your favorite stocks and monitor their performance
        </div>
      </div>

      <div className="grid" container spacing={3}>
        <div className="grid" item xs={12}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header
              title={
                <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <div  variant="h6">
                    {watchlists.length > 0 ? watchlists[activeWatchlist]?.name : 'No Watchlists'}
                  </div>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={`${watchlistItems.length} stocks`} 
                    size="small" 
                    color="primary" 
                    variant="outlined"
                  />
                </div>
              }
              action={
                <div  sx={{ display: 'flex', gap: 1 }}>
                  <div  title="Refresh">
                    <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleRefresh}>
                      <Refresh />
                    </button>
                  </div>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="outlined"
                    startIcon={<Add />}
                    onClick={() => setCreateDialogOpen(true)}
                  >
                    New Watchlist
                  </button>
                </div>
              }
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              {watchlists.length > 0 && (
                <div  sx={{ mb: 3 }}>
                  <div className="border-b border-gray-200"
                    value={activeWatchlist}
                    onChange={(e, newValue) => setActiveWatchlist(newValue)}
                    variant="scrollable"
                    scrollButtons="auto"
                  >
                    {watchlists.map((watchlist, index) => (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" 
                        key={watchlist.id} 
                        label={watchlist.name}
                        icon={
                          <button className="p-2 rounded-full hover:bg-gray-100"
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteWatchlist(watchlist.id);
                            }}
                          >
                            <Delete fontSize="small" />
                          </button>
                        }
                        iconPosition="end"
                      />
                    ))}
                  </div>
                </div>
              )}

              {watchlists.length > 0 && watchlists[activeWatchlist] && (
                <div  sx={{ mb: 3 }}>
                  <Autocomplete
                    options={allStocks}
                    getOptionLabel={(option) => option.symbol || option}
                    renderInput={(params) => (
                      <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                </div>
              )}

              {loading && <div className="w-full bg-gray-200 rounded-full h-2" />}
              {renderWatchlistTable()}
            </div>
          </div>
        </div>
      </div>

      {/* Create Watchlist Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={createDialogOpen} onClose={() => setCreateDialogOpen(false)}>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Create New Watchlist</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            autoFocus
            margin="dense"
            label="Watchlist Name"
            fullWidth
            variant="outlined"
            value={newWatchlistName}
            onChange={(e) => setNewWatchlistName(e.target.value)}
          />
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            margin="dense"
            label="Description (optional)"
            fullWidth
            variant="outlined"
            multiline
            rows={2}
            value={newWatchlistDescription}
            onChange={(e) => setNewWatchlistDescription(e.target.value)}
          />
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setCreateDialogOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleCreateWatchlist} variant="contained">Create</button>
        </div>
      </div>

      {/* Snackbar for notifications */}
      <div className="fixed bottom-4 right-4 bg-gray-800 text-white p-4 rounded-md shadow-lg"
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </div>
      </div>
    </div>
  );
};

export default Watchlist;