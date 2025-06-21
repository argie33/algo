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
import { Bar } from 'react-chartjs-2';
import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { javascript } from '@codemirror/lang-javascript';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';

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
  const [validateStatus, setValidateStatus] = useState(null);
  const [validateMsg, setValidateMsg] = useState('');
  const [activeTab, setActiveTab] = useState('equity');
  const [isRunning, setIsRunning] = useState(false);

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
    // Fetch user strategies from backend
    fetch(`${API_BASE}/backtest/strategies`).then(r => r.json()).then(d => setSavedStrategies(d.strategies || []));
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
    setIsRunning(true);
    setError(null);
    setResult(null);
    setLogs('');
    try {
      let res, data;
      if (useCustomCode) {
        res = await fetch(`${API_BASE}/backtest/run-python`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ strategy: pythonCode })
        });
        data = await res.json();
      } else {
        const body = { ...params, ...strategyParams, strategy: params.strategy };
        res = await fetch(`${API_BASE}/backtest/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        data = await res.json();
      }
      if (!data.success) throw new Error(data.error || 'Backtest failed');
      setResult(data);
      setLogs(data.logs || data.stdout || '');
      setActiveTab('equity');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setIsRunning(false);
    }
  };

  const handleStop = () => {
    // For now, just set running to false and loading to false (simulate stop)
    setIsRunning(false);
    setLoading(false);
    setError('Backtest stopped by user.');
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

  const handleSaveStrategy = async () => {
    if (!pythonCode.trim()) return;
    const name = prompt('Enter a name for this strategy:');
    if (!name) return;
    const res = await fetch(`${API_BASE}/backtest/strategies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, code: pythonCode, language: 'python' })
    });
    const data = await res.json();
    setSavedStrategies(prev => [...prev, data.strategy]);
  };

  const handleLoadStrategy = (code) => {
    setPythonCode(code);
    setUseCustomCode(true);
  };

  const handleDeleteStrategy = async (id) => {
    await fetch(`${API_BASE}/backtest/strategies/${id}`, { method: 'DELETE' });
    setSavedStrategies(prev => prev.filter(s => s.id !== id));
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

  // Validate custom code (Python or JS)
  const handleValidate = async () => {
    setValidateStatus('pending');
    setValidateMsg('');
    try {
      const res = await fetch(`${API_BASE}/backtest/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy: pythonCode })
      });
      const data = await res.json();
      if (data.valid) {
        setValidateStatus('success');
        setValidateMsg('Code is valid!');
      } else {
        setValidateStatus('error');
        setValidateMsg(data.error || 'Invalid code');
      }
    } catch (e) {
      setValidateStatus('error');
      setValidateMsg(e.message);
    }
  };

  // Helper to compute drawdown series from equity
  const getDrawdownSeries = (equity) => {
    if (!equity || equity.length === 0) return [];
    let peak = equity[0].value;
    return equity.map(point => {
      if (point.value > peak) peak = point.value;
      return { date: point.date, drawdown: ((point.value - peak) / peak) * 100 };
    });
  };

  // Helper: get trade markers for equity curve
  const getTradeMarkers = (equity, trades) => {
    if (!equity || !trades) return [];
    return trades.map(trade => {
      const idx = equity.findIndex(e => e.date === trade.date);
      return idx >= 0 ? { x: idx, y: equity[idx].value, action: trade.action, price: trade.price } : null;
    }).filter(Boolean);
  };

  const handleRenameStrategy = async (id) => {
    const strategy = savedStrategies.find(s => s.id === id);
    if (!strategy) return;
    const newName = prompt('Enter a new name for this strategy:', strategy.name);
    if (!newName || newName === strategy.name) return;
    // Update backend (simulate PATCH by delete+add)
    await fetch(`${API_BASE}/backtest/strategies/${id}`, { method: 'DELETE' });
    const res = await fetch(`${API_BASE}/backtest/strategies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName, code: strategy.code, language: strategy.language })
    });
    const data = await res.json();
    setSavedStrategies(prev => prev.filter(s => s.id !== id).concat(data.strategy));
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
              <Box display="flex" flexWrap="wrap" gap={2}>
                {paramConfig.map(param => (
                  <TextField
                    key={param.name}
                    label={param.label}
                    type={param.type}
                    value={strategyParams[param.name] ?? param.default}
                    onChange={e => handleStrategyParamChange(param.name, e.target.value)}
                    size="small"
                    sx={{ width: 180 }}
                  />
                ))}
              </Box>
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
                <Paper sx={{ p: 0, mb: 2, background: '#f7f7f7' }}>
                  <CodeMirror
                    value={pythonCode}
                    height="300px"
                    extensions={[python()]}
                    onChange={v => setPythonCode(v)}
                    theme="light"
                  />
                </Paper>
                <Button variant="outlined" startIcon={<SaveIcon />} onClick={handleSaveStrategy} sx={{ mb: 2, mr: 2 }}>Save Strategy</Button>
              </Grid>
            ) : null}
            <Grid item xs={12}>
              <Button
                variant="contained"
                color="primary"
                startIcon={<PlayArrow />}
                onClick={handleRun}
                disabled={loading || isRunning}
                sx={{ minWidth: 160 }}
              >
                {loading || isRunning ? <CircularProgress size={24} color="inherit" /> : 'Run Backtest'}
              </Button>
              <Button
                variant="outlined"
                color="secondary"
                startIcon={<Refresh />}
                onClick={() => { setParams(defaultParams); setResult(null); setError(null); setPythonCode(''); setStrategyParams({}); }}
                sx={{ ml: 2 }}
                disabled={loading || isRunning}
              >
                Reset
              </Button>
              <Button
                variant="outlined"
                color="error"
                onClick={handleStop}
                sx={{ ml: 2 }}
                disabled={!isRunning}
              >
                Stop
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}
      {result && (
        <Paper sx={{ p: 3 }}>
          <Tabs value={activeTab} onChange={(_, v) => setActiveTab(v)} sx={{ mb: 2 }}>
            <Tab label="Equity Curve" value="equity" />
            <Tab label="Drawdown" value="drawdown" />
            <Tab label="Trades" value="trades" />
            <Tab label="Logs" value="logs" />
            <Tab label="Summary" value="summary" />
          </Tabs>
          {activeTab === 'equity' && result.equity && (
            <Box mb={2}>
              <Typography variant="subtitle2">Equity Curve</Typography>
              <Line
                data={{
                  labels: result.equity.map(p => p.date),
                  datasets: [
                    {
                      label: 'Equity Curve',
                      data: result.equity.map(p => p.value),
                      borderColor: '#1976d2',
                      fill: false,
                      pointRadius: 0
                    },
                    ...getTradeMarkers(result.equity, result.trades).map(marker => ({
                      label: marker.action,
                      data: [{ x: marker.x, y: marker.y }],
                      pointBackgroundColor: marker.action === 'BUY' ? '#43a047' : '#e53935',
                      pointBorderColor: marker.action === 'BUY' ? '#43a047' : '#e53935',
                      pointRadius: 6,
                      type: 'scatter',
                      showLine: false
                    }))
                  ]
                }}
                options={{
                  responsive: true,
                  plugins: { legend: { display: false } },
                  scales: { x: { display: false } }
                }}
              />
            </Box>
          )}
          {activeTab === 'drawdown' && result.equity && (
            <Box mb={2}>
              <Typography variant="subtitle2">Drawdown Chart</Typography>
              <Bar
                data={{
                  labels: getDrawdownSeries(result.equity).map(p => p.date),
                  datasets: [{
                    label: 'Drawdown (%)',
                    data: getDrawdownSeries(result.equity).map(p => p.drawdown),
                    backgroundColor: '#ff7043',
                  }]
                }}
                options={{
                  responsive: true,
                  plugins: { legend: { display: false } },
                  scales: { y: { min: Math.min(...getDrawdownSeries(result.equity).map(p => p.drawdown)), max: 0 } }
                }}
              />
            </Box>
          )}
          {activeTab === 'trades' && result.trades && result.trades.length > 0 && (
            <Box mt={3}>
              <Typography variant="subtitle2">Trade Statistics</Typography>
              <TableContainer component={Paper} sx={{ mb: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Date</TableCell>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell>Price</TableCell>
                      <TableCell>Shares</TableCell>
                      <TableCell>PnL</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {result.trades.map((t, i) => (
                      <TableRow key={i}>
                        <TableCell>{t.date}</TableCell>
                        <TableCell>{t.symbol}</TableCell>
                        <TableCell>{t.action}</TableCell>
                        <TableCell>{t.price}</TableCell>
                        <TableCell>{t.quantity || t.shares}</TableCell>
                        <TableCell>{t.pnl !== undefined ? t.pnl.toFixed(2) : ''}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <Button variant="outlined" sx={{ mb: 2 }} onClick={handleExportTrades}>Export Trades (CSV)</Button>
            </Box>
          )}
          {activeTab === 'logs' && (
            <Box mt={2}>
              <Typography variant="subtitle2" color="text.secondary">Backtest Logs / Output</Typography>
              <Paper sx={{ p: 2, fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre', overflowX: 'auto', background: '#f7f7f7' }}>
                {logs}
              </Paper>
              <Button variant="outlined" startIcon={<DownloadIcon />} sx={{ mb: 2, mt: 2 }} onClick={handleDownloadLogs}>Download Logs</Button>
            </Box>
          )}
          {activeTab === 'summary' && result.metrics && (
            <Box mb={2}>
              <Typography variant="subtitle1" fontWeight="bold">Performance Summary</Typography>
              <Grid container spacing={2}>
                <Grid item xs={6} md={3}><Chip label={`Total Return: ${result.metrics.totalReturn?.toFixed(2)}%`} color="success" /></Grid>
                <Grid item xs={6} md={3}><Chip label={`Annualized: ${result.metrics.annualizedReturn?.toFixed(2)}%`} color="info" /></Grid>
                <Grid item xs={6} md={3}><Chip label={`Sharpe: ${result.metrics.sharpeRatio?.toFixed(2)}`} color="primary" /></Grid>
                <Grid item xs={6} md={3}><Chip label={`Max Drawdown: ${result.metrics.maxDrawdown?.toFixed(2)}%`} color="warning" /></Grid>
                <Grid item xs={6} md={3}><Chip label={`Volatility: ${result.metrics.volatility?.toFixed(2)}%`} color="default" /></Grid>
                <Grid item xs={6} md={3}><Chip label={`Win Rate: ${result.metrics.winRate?.toFixed(2)}%`} color="success" /></Grid>
                <Grid item xs={6} md={3}><Chip label={`Profit Factor: ${result.metrics.profitFactor?.toFixed(2)}`} color="info" /></Grid>
                <Grid item xs={6} md={3}><Chip label={`Trades: ${result.metrics.totalTrades}`} color="secondary" /></Grid>
              </Grid>
            </Box>
          )}
          <Button variant="outlined" startIcon={<FileDownloadIcon />} sx={{ mb: 2, mr: 2 }} onClick={handleExport}>Export Results</Button>
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
        </Paper>
      )}
      {useCustomCode && (
        <Card sx={{ mt: 4 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>Saved Strategies</Typography>
            <TableContainer component={Paper} sx={{ mb: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {savedStrategies.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell>{s.name}</TableCell>
                      <TableCell>
                        <Button size="small" onClick={() => handleLoadStrategy(s.code)}>Load</Button>
                        <Button size="small" onClick={() => handleRenameStrategy(s.id)}>Rename</Button>
                        <Button size="small" color="error" onClick={() => handleDeleteStrategy(s.id)}>Delete</Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}
    </Container>
  );
}
