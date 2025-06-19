import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, Container, Typography, Card, CardContent, Button, TextField, MenuItem, Grid, CircularProgress, Alert, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip
} from '@mui/material';
import { Assessment, PlayArrow, Refresh } from '@mui/icons-material';
import Autocomplete from '@mui/material/Autocomplete';
import { Line } from 'react-chartjs-2';
import FileDownloadIcon from '@mui/icons-material/FileDownload';

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
  const [symbols, setSymbols] = useState([]);
  const [strategies, setStrategies] = useState([]);
  const [strategyParams, setStrategyParams] = useState({});
  const [strategyCode, setStrategyCode] = useState('');

  // Helper: get param config for selected strategy (could be from backend or hardcoded)
  const paramConfig = useMemo(() => {
    const strat = strategies.find(s => s.id === params.strategy);
    if (!strat) return [];
    // Example: parse from strat.code or attach config in backend
    if (strat.id === 'moving_average_crossover') {
      return [
        { name: 'shortPeriod', label: 'Short MA Period', type: 'number', default: 20 },
        { name: 'longPeriod', label: 'Long MA Period', type: 'number', default: 50 }
      ];
    }
    if (strat.id === 'rsi_strategy') {
      return [
        { name: 'rsiOversold', label: 'RSI Oversold', type: 'number', default: 30 },
        { name: 'rsiOverbought', label: 'RSI Overbought', type: 'number', default: 70 }
      ];
    }
    return [];
  }, [strategies, params.strategy]);

  useEffect(() => {
    // Fetch symbols
    fetch(`${API_BASE}/backtest/symbols`).then(r => r.json()).then(d => setSymbols(d.symbols || []));
    // Fetch strategies/templates
    fetch(`${API_BASE}/backtest/templates`).then(r => r.json()).then(d => setStrategies(d.templates || []));
  }, []);

  useEffect(() => {
    const strat = strategies.find(s => s.id === params.strategy);
    setStrategyCode(strat?.code || '');
    // Set default param values
    if (paramConfig.length) {
      const defaults = {};
      paramConfig.forEach(p => { defaults[p.name] = p.default; });
      setStrategyParams(defaults);
    }
  }, [params.strategy, strategies, paramConfig]);

  const handleChange = (field, value) => {
    setParams(prev => ({ ...prev, [field]: value }));
  };

  const handleStrategyParamChange = (name, value) => {
    setStrategyParams(prev => ({ ...prev, [name]: value }));
  };

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...params, ...strategyParams })
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

  const handleExport = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `backtest_${params.symbol}_${params.strategy}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleStrategyChange = (id) => {
    const strat = strategies.find(s => s.id === id);
    handleChange('strategy', id);
    // Optionally parse params from strat.code or add UI for params
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
              <Autocomplete
                options={symbols.map(s => s.symbol)}
                value={params.symbol}
                onChange={(_, v) => handleChange('symbol', v || '')}
                renderInput={(props) => <TextField {...props} label="Symbol" fullWidth size="small" />}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                select
                label="Strategy"
                value={params.strategy}
                onChange={e => handleStrategyChange(e.target.value)}
                fullWidth
                size="small"
              >
                {strategies.map(s => (
                  <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField label="Start Date" type="date" value={params.startDate} onChange={e => handleChange('startDate', e.target.value)} fullWidth size="small" InputLabelProps={{ shrink: true }} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField label="End Date" type="date" value={params.endDate} onChange={e => handleChange('endDate', e.target.value)} fullWidth size="small" InputLabelProps={{ shrink: true }} />
            </Grid>
            <Grid item xs={12}>
              {paramConfig.map(param => (
                <TextField
                  key={param.name}
                  label={param.label}
                  type={param.type}
                  value={strategyParams[param.name] ?? param.default}
                  onChange={e => handleStrategyParamChange(param.name, e.target.value)}
                  size="small"
                  sx={{ mr: 2, mb: 2, width: 180 }}
                />
              ))}
            </Grid>
            <Grid item xs={12}>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>Strategy Code Preview</Typography>
              <Paper sx={{ p: 2, mb: 2, fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre', overflowX: 'auto', background: '#f7f7f7' }}>
                {strategyCode || 'Select a strategy to preview code.'}
              </Paper>
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
          <Button variant="outlined" startIcon={<FileDownloadIcon />} sx={{ mb: 2 }} onClick={handleExport}>Export Results</Button>
          {/* Performance Chart */}
          {result.equityCurve && (
            <Box mb={2}>
              <Line
                data={{
                  labels: result.equityCurve.map(p => p.date),
                  datasets: [{
                    label: 'Equity Curve',
                    data: result.equityCurve.map(p => p.value),
                    borderColor: '#1976d2',
                    fill: false
                  }]
                }}
                options={{ responsive: true, plugins: { legend: { display: false } } }}
              />
            </Box>
          )}
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
