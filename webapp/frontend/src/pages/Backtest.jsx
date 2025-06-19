import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, Container, Typography, Card, CardContent, Button, TextField, MenuItem, Grid, CircularProgress, Alert, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip
} from '@mui/material';
import { Assessment, PlayArrow, Refresh } from '@mui/icons-material';
import Autocomplete from '@mui/material/Autocomplete';
import { Line } from 'react-chartjs-2';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import TextareaAutosize from '@mui/material/TextareaAutosize';
import DownloadIcon from '@mui/icons-material/Download';
import SaveIcon from '@mui/icons-material/Save';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';

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
  const [pythonCode, setPythonCode] = useState('');
  const [useCustomCode, setUseCustomCode] = useState(false);
  const [logs, setLogs] = useState('');
  const [savedStrategies, setSavedStrategies] = useState([]);
  const [showApiExample, setShowApiExample] = useState(false);

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

  // Save/load strategies in localStorage
  useEffect(() => {
    const saved = JSON.parse(localStorage.getItem('backtest_strategies') || '[]');
    setSavedStrategies(saved);
  }, []);

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
    setLogs('');
    try {
      const body = useCustomCode
        ? { ...params, strategy_code: pythonCode, language: 'python' }
        : { ...params, ...strategyParams, strategy: params.strategy };
      const res = await fetch(`${API_BASE}/backtest/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Backtest failed');
      setResult(data);
      setLogs(data.logs || data.stdout || '');
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

  const handleDownloadLogs = () => {
    if (!logs) return;
    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `backtest_logs_${params.symbol}_${params.strategy || 'custom'}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleStrategyChange = (id) => {
    const strat = strategies.find(s => s.id === id);
    handleChange('strategy', id);
    // Optionally parse params from strat.code or add UI for params
  };

  const handleSaveStrategy = () => {
    if (!pythonCode.trim()) return;
    const name = prompt('Enter a name for this strategy:');
    if (!name) return;
    const newStrategy = { name, code: pythonCode };
    const updated = [...savedStrategies, newStrategy];
    setSavedStrategies(updated);
    localStorage.setItem('backtest_strategies', JSON.stringify(updated));
  };

  const handleLoadStrategy = (code) => {
    setPythonCode(code);
    setUseCustomCode(true);
  };

  const handleExportTrades = () => {
    if (!result?.trades?.length) return;
    const csv = [
      'Date,Action,Price,Shares,PnL',
      ...result.trades.map(t => `${t.date},${t.action},${t.price},${t.shares},${t.pnl}`)
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `backtest_trades_${params.symbol}_${params.strategy || 'custom'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const apiExample = `import requests\n\nurl = '${API_BASE}/backtest/run'\npayload = {\n    'symbol': '${params.symbol}',\n    'strategy_code': '''\n${pythonCode.replace(/'/g, "''")}\n''',\n    'language': 'python'\n}\nresponse = requests.post(url, json=payload)\nprint(response.json())`;

  const handleCopyApiExample = () => {
    navigator.clipboard.writeText(apiExample);
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
              <Button
                variant={useCustomCode ? 'contained' : 'outlined'}
                onClick={() => setUseCustomCode(!useCustomCode)}
                sx={{ mb: 2 }}
              >
                {useCustomCode ? 'Use Strategy Dropdown' : 'Write Custom Python Strategy'}
              </Button>
            </Grid>
            {useCustomCode ? (
              <Grid item xs={12}>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>Python Strategy Code</Typography>
                <TextareaAutosize
                  minRows={10}
                  style={{ width: '100%', fontFamily: 'monospace', fontSize: 14, background: '#f7f7f7', padding: 8, borderRadius: 4 }}
                  value={pythonCode}
                  onChange={e => setPythonCode(e.target.value)}
                  placeholder={'# Write your Python strategy here\ndef handle_data(context, data):\n    pass'}
                />
              </Grid>
            ) : (
              <>
                {/* ...existing code for strategy selection and preview... */}
              </>
            )}
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
          <Button variant="outlined" startIcon={<FileDownloadIcon />} sx={{ mb: 2, mr: 2 }} onClick={handleExport}>Export Results</Button>
          <Button variant="outlined" startIcon={<DownloadIcon />} sx={{ mb: 2, mr: 2 }} onClick={handleDownloadLogs}>Download Logs</Button>
          {result.trades?.length > 0 && (
            <Button variant="outlined" sx={{ mb: 2 }} onClick={handleExportTrades}>Export Trades (CSV)</Button>
          )}
          {/* API Example */}
          <Button variant="text" startIcon={<ContentCopyIcon />} sx={{ mb: 2, ml: 2 }} onClick={() => setShowApiExample(v => !v)}>
            {showApiExample ? 'Hide' : 'Show'} API Example
          </Button>
          {showApiExample && (
            <Paper sx={{ p: 2, fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre', overflowX: 'auto', background: '#f7f7f7', mb: 2 }}>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <span>Python API Example</span>
                <Button size="small" startIcon={<ContentCopyIcon />} onClick={handleCopyApiExample}>Copy</Button>
              </Box>
              {apiExample}
            </Paper>
          )}
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
          {/* Show logs/output if present */}
          {logs && (
            <Box mt={2}>
              <Typography variant="subtitle2" color="text.secondary">Backtest Logs / Output</Typography>
              <Paper sx={{ p: 2, fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre', overflowX: 'auto', background: '#f7f7f7' }}>
                {logs}
              </Paper>
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
