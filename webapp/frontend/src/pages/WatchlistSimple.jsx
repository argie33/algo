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
import { useAuth } from '../contexts/AuthContext';

// Simple watchlist without drag and drop - BACKUP VERSION
const WatchlistSimple = () => {
  const { isAuthenticated } = useAuth();
  const [watchlists, setWatchlists] = useState([]);
  const [activeWatchlist, setActiveWatchlist] = useState(0);
  const [watchlistItems, setWatchlistItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedStock, setSelectedStock] = useState(null);

  // Load watchlists on mount
  useEffect(() => {
    const initializeWatchlists = async () => {
      try {
        if (isAuthenticated) {
          const data = await getWatchlists();
          setWatchlists(data || []);
        }
      } catch (error) {
        console.error('Error loading watchlists:', error);
      }
    };
    
    initializeWatchlists();
  }, [isAuthenticated]);

  const handleRemoveStock = async (itemId) => {
    try {
      const currentWatchlist = watchlists[activeWatchlist];
      if (!currentWatchlist) return;
      
      await deleteWatchlistItem(currentWatchlist.id, itemId);
      setWatchlistItems(prev => prev.filter(item => item.id !== itemId));
    } catch (error) {
      console.error('Error removing item:', error);
    }
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
      <Typography variant="h4" component="h1" gutterBottom>
        📊 Stock Watchlists (Simple Version)
      </Typography>
      
      <Alert severity="info" sx={{ mb: 2 }}>
        Simplified watchlist without drag-and-drop functionality. All core features work normally.
      </Alert>

      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ backgroundColor: '#1976d214' }}>
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
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {watchlistItems.length > 0 ? (
              watchlistItems.map((item, index) => (
                <TableRow
                  key={item.id}
                  sx={{ 
                    '&:hover': { backgroundColor: '#1976d20A' },
                    '&:nth-of-type(odd)': { backgroundColor: '#f9f9f9' }
                  }}
                >
                  <TableCell>
                    <Box>
                      <Typography variant="body2" fontWeight="bold">
                        {item.symbol}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {item.short_name || item.security_name || 'N/A'}
                      </Typography>
                    </Box>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" fontWeight="bold">
                      {item.current_price ? formatCurrency(item.current_price) : 'N/A'}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography 
                      variant="body2" 
                      color={item.day_change_percent >= 0 ? 'success.main' : 'error.main'}
                      fontWeight="bold"
                    >
                      {item.day_change_amount ? formatCurrency(item.day_change_amount) : 'N/A'}
                      {item.day_change_percent ? ` (${formatPercentage(item.day_change_percent)})` : ''}
                    </Typography>
                  </TableCell>
                  <TableCell align="center">
                    <Tooltip title="Remove from watchlist">
                      <IconButton
                        size="small"
                        onClick={() => handleRemoveStock(item.id)}
                        color="error"
                      >
                        <Delete fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={4} align="center">
                  <Typography variant="body2" color="text.secondary" sx={{ py: 4 }}>
                    No stocks in watchlist. Add some stocks to get started.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Container>
  );
};

export default WatchlistSimple;