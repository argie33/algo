import React, { useState } from 'react';
import {
  Box, Container, Typography, Card, CardContent, Button, TextField, MenuItem, Grid, CircularProgress, Alert, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip
} from '@mui/material';
import { Assessment, PlayArrow, Refresh } from '@mui/icons-material';

const API_BASE = import.meta.env.VITE_API_URL || '';

const defaultParams = {
  symbol: '',
  strategy: '',
  startDate: '',
  endDate: ''
};

export default function Backtest() {
  const [params, setParams] = useState(defaultParams);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (field, value) => {
    setParams(prev => ({ ...prev, [field]: value }));
  };

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Backtest failed');
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Box display="flex" alignItems="center" gap={2} mb={3}>
        <Assessment color="primary" fontSize="large" />
        <Typography variant="h4" fontWeight="bold">Backtester</Typography>
      </Box>
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Run a Backtest</Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField label="Symbol" value={params.symbol} onChange={e => handleChange('symbol', e.target.value)} fullWidth size="small" placeholder="AAPL" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField label="Strategy" value={params.strategy} onChange={e => handleChange('strategy', e.target.value)} fullWidth size="small" placeholder="mean_reversion" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField label="Start Date" type="date" value={params.startDate} onChange={e => handleChange('startDate', e.target.value)} fullWidth size="small" InputLabelProps={{ shrink: true }} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField label="End Date" type="date" value={params.endDate} onChange={e => handleChange('endDate', e.target.value)} fullWidth size="small" InputLabelProps={{ shrink: true }} />
            </Grid>
            <Grid item xs={12}>
              <Button variant="contained" color="primary" startIcon={<PlayArrow />} onClick={handleRun} disabled={loading} sx={{ minWidth: 160 }}>
                {loading ? <CircularProgress size={24} color="inherit" /> : 'Run Backtest'}
              </Button>
              <Button variant="outlined" color="secondary" startIcon={<Refresh />} onClick={() => { setParams(defaultParams); setResult(null); setError(null); }} sx={{ ml: 2 }} disabled={loading}>
                Reset
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
      {result && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6" gutterBottom>Backtest Results</Typography>
          {result.performance && (
            <Box mb={2}>
              <Chip label={`Total Return: ${result.performance.totalReturn || 'N/A'}`} color="success" sx={{ mr: 1 }} />
              <Chip label={`Sharpe Ratio: ${result.performance.sharpeRatio || 'N/A'}`} color="info" sx={{ mr: 1 }} />
              <Chip label={`Max Drawdown: ${result.performance.maxDrawdown || 'N/A'}`} color="warning" />
            </Box>
          )}
          {result.trades && result.trades.length > 0 && (
            <TableContainer component={Paper} sx={{ mt: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell>Action</TableCell>
                    <TableCell>Price</TableCell>
                    <TableCell>Shares</TableCell>
                    <TableCell>PnL</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {result.trades.map((trade, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{trade.date}</TableCell>
                      <TableCell>{trade.action}</TableCell>
                      <TableCell>{trade.price}</TableCell>
                      <TableCell>{trade.shares}</TableCell>
                      <TableCell>{trade.pnl}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Paper>
      )}
    </Container>
  );
}
