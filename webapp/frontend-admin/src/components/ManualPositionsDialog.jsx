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

const BROKERS = [
  'Interactive Brokers',
  'Fidelity',
  'Charles Schwab',
  'E*TRADE',
  'TD Ameritrade',
  'Webull',
  'Robinhood',
  'Other',
];

export default function ManualPositionsDialog() {
  const [open, setOpen] = useState(false);
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [formData, setFormData] = useState({
    symbol: '',
    quantity: '',
    average_cost: '',
    current_price: '',
    broker: '',
    broker_account_id: '',
    purchase_date: '',
    notes: '',
  });

  // Fetch manual positions on mount
  useEffect(() => {
    if (open) {
      fetchPositions();
    }
  }, [open]);

  const fetchPositions = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/portfolio/manual-positions');
      const data = await response.json();
      if (data.success) {
        // Handle different response structures
        const positionsData = data.data || [];
        setPositions(Array.isArray(positionsData) ? positionsData : []);
      } else {
        setError(data.error || 'Failed to fetch positions');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleAddPosition = () => {
    setEditingId(null);
    setFormData({
      symbol: '',
      quantity: '',
      average_cost: '',
      current_price: '',
      broker: '',
      broker_account_id: '',
      purchase_date: '',
      notes: '',
    });
    setIsFormOpen(true);
  };

  const handleEditPosition = (position) => {
    setEditingId(position.id);
    setFormData({
      symbol: position.symbol,
      quantity: position.quantity.toString(),
      average_cost: position.average_cost.toString(),
      current_price: position.current_price ? position.current_price.toString() : '',
      broker: position.broker || '',
      broker_account_id: position.broker_account_id || '',
      purchase_date: position.purchase_date ? position.purchase_date.split('T')[0] : '',
      notes: position.notes || '',
    });
    setIsFormOpen(true);
  };

  const handleDeletePosition = async (id) => {
    if (window.confirm('Are you sure you want to delete this position?')) {
      try {
        const response = await fetch(`/api/portfolio/manual-positions/${id}`, {
          method: 'DELETE',
        });
        const data = await response.json();
        if (data.success) {
          setPositions(positions.filter(p => p.id !== id));
          setError(null);
        } else {
          setError(data.error || 'Failed to delete position');
        }
      } catch (err) {
        setError(err.message);
      }
    }
  };

  const handleSavePosition = async () => {
    setError(null);
    try {
      const url = editingId
        ? `/api/portfolio/manual-positions/${editingId}`
        : '/api/portfolio/manual-positions';
      const method = editingId ? 'PATCH' : 'POST';

      const payload = {
        ...formData,
        quantity: parseFloat(formData.quantity),
        average_cost: parseFloat(formData.average_cost),
        current_price: formData.current_price ? parseFloat(formData.current_price) : null,
      };

      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (data.success) {
        setIsFormOpen(false);
        fetchPositions();
      } else {
        setError(data.error || 'Failed to save position');
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleFormChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const calculateMetrics = (position) => {
    const costBasis = position.quantity * position.average_cost;
    const marketValue = position.quantity * (position.current_price || position.average_cost);
    const unrealizedGain = marketValue - costBasis;
    const unrealizedGainPct = costBasis > 0 ? (unrealizedGain / costBasis) * 100 : 0;
    return { costBasis, marketValue, unrealizedGain, unrealizedGainPct };
  };

  return (
    <>
      <Button
        variant="contained"
        color="primary"
        startIcon={<AddIcon />}
        onClick={() => setOpen(true)}
        sx={{ mb: 2 }}
      >
        Manage Manual Positions
      </Button>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>Manual Positions Management</DialogTitle>
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
                placeholder="e.g., AAPL"
                required
              />
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
                label="Average Cost"
                name="average_cost"
                type="number"
                value={formData.average_cost}
                onChange={handleFormChange}
                inputProps={{ step: '0.01' }}
                required
              />
              <TextField
                label="Current Price"
                name="current_price"
                type="number"
                value={formData.current_price}
                onChange={handleFormChange}
                inputProps={{ step: '0.01' }}
              />
              <FormControl fullWidth>
                <InputLabel>Broker</InputLabel>
                <Select
                  name="broker"
                  value={formData.broker}
                  onChange={handleFormChange}
                  label="Broker"
                >
                  {BROKERS.map(broker => (
                    <MenuItem key={broker} value={broker}>{broker}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <TextField
                label="Broker Account ID"
                name="broker_account_id"
                value={formData.broker_account_id}
                onChange={handleFormChange}
              />
              <TextField
                label="Purchase Date"
                name="purchase_date"
                type="date"
                value={formData.purchase_date}
                onChange={handleFormChange}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                label="Notes"
                name="notes"
                value={formData.notes}
                onChange={handleFormChange}
                multiline
                rows={2}
                sx={{ gridColumn: '1 / -1' }}
              />
              <Box sx={{ gridColumn: '1 / -1', display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                <Button onClick={() => setIsFormOpen(false)}>Cancel</Button>
                <Button
                  onClick={handleSavePosition}
                  variant="contained"
                  color="primary"
                >
                  {editingId ? 'Update' : 'Add'} Position
                </Button>
              </Box>
            </Box>
          ) : (
            <>
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={handleAddPosition}
                sx={{ mb: 2 }}
              >
                Add Position
              </Button>

              {loading ? (
                <p>Loading positions...</p>
              ) : positions.length === 0 ? (
                <Alert severity="info">No manual positions added yet.</Alert>
              ) : (
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Quantity</TableCell>
                        <TableCell align="right">Avg Cost</TableCell>
                        <TableCell align="right">Current Price</TableCell>
                        <TableCell align="right">Market Value</TableCell>
                        <TableCell align="right">Gain/Loss</TableCell>
                        <TableCell align="right">Gain/Loss %</TableCell>
                        <TableCell align="center">Broker</TableCell>
                        <TableCell align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {positions.map(position => {
                        const metrics = calculateMetrics(position);
                        return (
                          <TableRow key={position.id}>
                            <TableCell><strong>{position.symbol}</strong></TableCell>
                            <TableCell align="right">{position.quantity.toFixed(4)}</TableCell>
                            <TableCell align="right">${position.average_cost.toFixed(2)}</TableCell>
                            <TableCell align="right">
                              ${(position.current_price || position.average_cost).toFixed(2)}
                            </TableCell>
                            <TableCell align="right">
                              ${metrics.marketValue.toFixed(2)}
                            </TableCell>
                            <TableCell
                              align="right"
                              sx={{
                                color: metrics.unrealizedGain >= 0 ? 'green' : 'red',
                                fontWeight: 'bold',
                              }}
                            >
                              ${metrics.unrealizedGain.toFixed(2)}
                            </TableCell>
                            <TableCell
                              align="right"
                              sx={{
                                color: metrics.unrealizedGainPct >= 0 ? 'green' : 'red',
                                fontWeight: 'bold',
                              }}
                            >
                              {metrics.unrealizedGainPct.toFixed(2)}%
                            </TableCell>
                            <TableCell align="center">{position.broker || '—'}</TableCell>
                            <TableCell align="center">
                              <IconButton
                                size="small"
                                onClick={() => handleEditPosition(position)}
                                title="Edit"
                              >
                                <EditIcon fontSize="small" />
                              </IconButton>
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => handleDeletePosition(position.id)}
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
