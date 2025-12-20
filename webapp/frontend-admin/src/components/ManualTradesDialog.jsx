import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Box,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import AddIcon from '@mui/icons-material/Add';

const TRADE_TYPES = ['buy', 'sell'];
const STATUSES = ['filled', 'pending', 'cancelled'];

export default function ManualTradesDialog() {
  const [open, setOpen] = useState(false);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState({
    symbol: '',
    trade_type: 'buy',
    quantity: '',
    price: '',
    execution_date: '',
    status: 'filled',
  });

  // Fetch manual trades on mount
  useEffect(() => {
    if (open) {
      fetchTrades();
    }
  }, [open]);

  const fetchTrades = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/trades/manual');
      const data = await response.json();
      if (data.success) {
        // Handle different response structures
        const tradesData = data.data || [];
        setTrades(Array.isArray(tradesData) ? tradesData : []);
      } else {
        setError(data.error || 'Failed to fetch trades');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAddTrade = () => {
    setEditingId(null);
    setFormData({
      symbol: '',
      trade_type: 'buy',
      quantity: '',
      price: '',
      execution_date: new Date().toISOString().split('T')[0],
      status: 'filled',
    });
    setIsFormOpen(true);
  };

  const handleEditTrade = (trade) => {
    setEditingId(trade.id);
    setFormData({
      symbol: trade.symbol,
      trade_type: trade.trade_type,
      quantity: trade.quantity.toString(),
      price: trade.price.toString(),
      execution_date: trade.execution_date.split('T')[0],
      status: trade.status,
    });
    setIsFormOpen(true);
  };

  const handleDeleteTrade = async (id) => {
    if (window.confirm('Are you sure you want to delete this trade?')) {
      try {
        const response = await fetch(`/api/trades/manual/${id}`, {
          method: 'DELETE',
        });
        const data = await response.json();
        if (data.success) {
          setTrades(trades.filter(t => t.id !== id));
          setError(null);
        } else {
          setError(data.error || 'Failed to delete trade');
        }
      } catch (err) {
        setError(err.message);
      }
    }
  };

  const handleSaveTrade = async () => {
    setError(null);
    try {
      const url = editingId
        ? `/api/trades/manual/${editingId}`
        : '/api/trades/manual';
      const method = editingId ? 'PATCH' : 'POST';

      const payload = {
        ...formData,
        quantity: parseFloat(formData.quantity),
        price: parseFloat(formData.price),
      };

      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (data.success) {
        setIsFormOpen(false);
        fetchTrades();
      } else {
        setError(data.error || 'Failed to save trade');
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleFormChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const calculateTradeValue = (quantity, price) => {
    return quantity * price;
  };

  return (
    <>
      <Button
        variant="contained"
        color="primary"
        startIcon={<AddIcon />}
        onClick={() => setOpen(true)}
        sx={{ mb: 2, ml: 1 }}
      >
        Record Manual Trade
      </Button>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>Manual Trade Entry</DialogTitle>
        <DialogContent>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          {isFormOpen ? (
            <Box sx={{ mt: 2, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
              <TextField
                label="Symbol"
                name="symbol"
                value={formData.symbol}
                onChange={handleFormChange}
                placeholder="e.g., TSLA"
                required
              />
              <FormControl fullWidth required>
                <InputLabel>Trade Type</InputLabel>
                <Select
                  name="trade_type"
                  value={formData.trade_type}
                  onChange={handleFormChange}
                  label="Trade Type"
                >
                  {TRADE_TYPES.map(type => (
                    <MenuItem key={type} value={type}>{type.toUpperCase()}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                label="Quantity"
                name="quantity"
                type="number"
                value={formData.quantity}
                onChange={handleFormChange}
                inputProps={{ step: '0.001' }}
                required
              />
              <TextField
                label="Price"
                name="price"
                type="number"
                value={formData.price}
                onChange={handleFormChange}
                inputProps={{ step: '0.01' }}
                required
              />
              <TextField
                label="Execution Date"
                name="execution_date"
                type="date"
                value={formData.execution_date}
                onChange={handleFormChange}
                InputLabelProps={{ shrink: true }}
                required
              />
              <FormControl fullWidth>
                <InputLabel>Status</InputLabel>
                <Select
                  name="status"
                  value={formData.status}
                  onChange={handleFormChange}
                  label="Status"
                >
                  {STATUSES.map(status => (
                    <MenuItem key={status} value={status}>{status.toUpperCase()}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Box sx={{ gridColumn: '1 / -1', display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                <Button onClick={() => setIsFormOpen(false)}>Cancel</Button>
                <Button
                  onClick={handleSaveTrade}
                  variant="contained"
                  color="primary"
                >
                  {editingId ? 'Update' : 'Add'} Trade
                </Button>
              </Box>
            </Box>
          ) : (
            <>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={handleAddTrade}
                sx={{ mb: 2 }}
              >
                Add Trade
              </Button>

              {loading ? (
                <p>Loading trades...</p>
              ) : trades.length === 0 ? (
                <Alert severity="info">No manual trades recorded yet.</Alert>
              ) : (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                        <TableCell>Date</TableCell>
                        <TableCell>Symbol</TableCell>
                        <TableCell>Type</TableCell>
                        <TableCell align="right">Qty</TableCell>
                        <TableCell align="right">Price</TableCell>
                        <TableCell align="right">Total Value</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {trades.map(trade => {
                        const quantity = parseFloat(trade.quantity);
                        const price = parseFloat(trade.price);
                        const totalValue = calculateTradeValue(quantity, price);
                        return (
                          <TableRow key={trade.id}>
                            <TableCell>{trade.execution_date}</TableCell>
                            <TableCell><strong>{trade.symbol}</strong></TableCell>
                            <TableCell>{trade.trade_type.toUpperCase()}</TableCell>
                            <TableCell align="right">{quantity.toFixed(4)}</TableCell>
                            <TableCell align="right">${price.toFixed(2)}</TableCell>
                            <TableCell align="right">${totalValue.toFixed(2)}</TableCell>
                            <TableCell>{trade.status}</TableCell>
                            <TableCell align="center">
                              <IconButton
                                size="small"
                                onClick={() => handleEditTrade(trade)}
                                title="Edit"
                              >
                                <EditIcon fontSize="small" />
                              </IconButton>
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => handleDeleteTrade(trade.id)}
                                title="Delete"
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
