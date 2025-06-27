import React, { useState, useEffect, useMemo } from 'react';
import {
  Box, Container, Typography, Card, CardContent, Button, TextField, MenuItem, Grid, CircularProgress, Alert, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Chip
} from '@mui/material';
import { Analytics, PlayArrow, Refresh } from '@mui/icons-material';
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
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import Tooltip from '@mui/material/Tooltip';

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
  const [customMetricTab, setCustomMetricTab] = useState(null);

  // Parameter sweep state 
  const [sweepParams, setSweepParams] = useState({});
  const [sweepResults, setSweepResults] = useState([]);
  const [sweepRunning, setSweepRunning] = useState(false);
  const [sweepProgress, setSweepProgress] = useState({ current: 0, total: 0 });

  // --- BATCH QUEUE STATE ---
  const [batchQueue, setBatchQueue] = useState([]); // [{params, status, result, error}]
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState(0);
  const [batchCancelled, setBatchCancelled] = useState(false);

  // --- STRATEGY VERSIONING ---
  const [strategyHistory, setStrategyHistory] = useState({}); // {strategyId: [versions]}

  // Helper: get param config for selected strategy (could be from backend or hardcoded)
  const paramConfig = useMemo(() => {
    const strat = Array.isArray(strategies) ? strategies.find(s => s.id === params.strategy) : null;
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
    const strat = Array.isArray(strategies) ? strategies.find(s => s.id === params.strategy) : null;
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
        // Custom code mode: send to /run-python
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
    const strat = Array.isArray(strategies) ? strategies.find(s => s.id === id) : null;
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
    saveStrategyVersion(data.strategy.id, pythonCode);
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
  const curlExample = `curl -X POST '${API_BASE}/backtest/run' \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    "symbol": "${params.symbol}",\n    "strategy_code": """\n${pythonCode.replace(/"/g, '\"')}\n""",\n    "language": "python"\n  }'`;

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

  // Helper: generate all combinations of sweep parameters
  const getSweepCombinations = () => {
    if (!paramConfig.length) return [];
    const keys = paramConfig.map(p => p.name);
    const values = keys.map(k => {
      const val = sweepParams[k];
      if (!val) return [strategyParams[k] ?? paramConfig.find(p => p.name === k)?.default];
      // Support comma-separated lists or ranges (e.g. 10,20,30 or 10-30:5)
      if (val.includes(',')) return val.split(',').map(v => parseFloat(v.trim()));
      if (val.includes('-') && val.includes(':')) {
        const [start, rest] = val.split('-');
        const [end, step] = rest.split(':');
        const arr = [];
        for (let i = parseFloat(start); i <= parseFloat(end); i += parseFloat(step)) arr.push(i);
        return arr;
      }
      return [parseFloat(val)];
    });
    // Cartesian product
    return values.reduce((a, b) => a.flatMap(d => b.map(e => [].concat(d, e))), [[]]).map(arr => {
      const obj = {};
      arr.forEach((v, i) => { obj[keys[i]] = v; });
      return obj;
    });
  };

  const handleSweepParamChange = (name, value) => {
    setSweepParams(prev => ({ ...prev, [name]: value }));
  };

  const handleRunSweep = async () => {
    const combos = getSweepCombinations();
    if (!combos.length) return;
    setSweepRunning(true);
    setSweepProgress({ current: 0, total: combos.length });
    setSweepResults([]);
    for (let i = 0; i < combos.length; ++i) {
      if (!sweepRunning) break;
      const combo = combos[i];
      const body = { ...params, ...combo, strategy: params.strategy };
      try {
        const res = await fetch(`${API_BASE}/backtest/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        const data = await res.json();
        setSweepResults(prev => [...prev, { params: combo, metrics: data.metrics, success: data.success, error: data.error }]);
      } catch (e) {
        setSweepResults(prev => [...prev, { params: combo, metrics: null, success: false, error: e.message }]);
      }
      setSweepProgress({ current: i + 1, total: combos.length });
    }
    setSweepRunning(false);
  };

  const handleStopSweep = () => {
    setSweepRunning(false);
  };

  // --- BATCH RUN LOGIC ---
  const handleBatchRun = async (paramGrid) => {
    setBatchQueue(paramGrid.map(p => ({ params: p, status: 'pending', result: null, error: null })));
    setBatchRunning(true);
    setBatchProgress(0);
    setBatchCancelled(false);
    let completed = 0;
    for (let i = 0; i < paramGrid.length; ++i) {
      if (batchCancelled) break;
      setBatchQueue(q => q.map((item, idx) => idx === i ? { ...item, status: 'running' } : item));
      try {
        const res = await fetch(`${API_BASE}/backtest/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...paramGrid[i], strategy: params.strategy })
        });
        const data = await res.json();
        setBatchQueue(q => q.map((item, idx) => idx === i ? { ...item, status: data.success ? 'done' : 'error', result: data.success ? data : null, error: data.success ? null : (data.error || 'Error') } : item));
      } catch (e) {
        setBatchQueue(q => q.map((item, idx) => idx === i ? { ...item, status: 'error', error: e.message } : item));
      }
      completed++;
      setBatchProgress(completed / paramGrid.length);
    }
    setBatchRunning(false);
  };
  const handleBatchCancel = () => { setBatchCancelled(true); setBatchRunning(false); };

  // --- STRATEGY VERSIONING LOGIC ---
  const saveStrategyVersion = (id, code) => {
    setStrategyHistory(h => ({ ...h, [id]: [...(h[id] || []), { code, date: new Date().toISOString() }] }));
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Box display="flex" alignItems="center" gap={2} mb={3}>
        <Analytics color="primary" fontSize="large" />
        <Typography variant="h4" fontWeight="bold">Backtester</Typography>
        <Tooltip title="Start a new blank strategy" arrow><Button variant="outlined" sx={{ ml: 2 }} onClick={() => { setPythonCode(''); setParams(defaultParams); setStrategyParams({}); setResult(null); setError(null); }}>New Strategy</Button></Tooltip>
      </Box>
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Run a Backtest</Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <Tooltip title="Choose a symbol to backtest" arrow><Autocomplete
                options={symbols.map(s => s.symbol)}
                value={params.symbol}
                onChange={(_, v) => handleChange('symbol', v || '')}
                renderInput={(props) => <TextField {...props} label="Symbol" fullWidth size="small" />}
              /></Tooltip>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Tooltip title="Select a strategy template or your own" arrow><TextField
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
              </TextField></Tooltip>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Tooltip title="Backtest start date" arrow><TextField label="Start Date" type="date" value={params.startDate} onChange={e => handleChange('startDate', e.target.value)} fullWidth size="small" InputLabelProps={{ shrink: true }} /></Tooltip>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Tooltip title="Backtest end date" arrow><TextField label="End Date" type="date" value={params.endDate} onChange={e => handleChange('endDate', e.target.value)} fullWidth size="small" InputLabelProps={{ shrink: true }} /></Tooltip>
            </Grid>
            <Grid item xs={12}>
              <Box display="flex" flexWrap="wrap" gap={2}>
                {paramConfig.map(param => (
                  <Tooltip key={param.name} title={param.label} arrow>
                    <TextField
                      label={param.label}
                      type={param.type}
                      value={strategyParams[param.name] ?? param.default}
                      onChange={e => handleStrategyParamChange(param.name, e.target.value)}
                      size="small"
                      sx={{ width: 180 }}
                    />
                  </Tooltip>
                ))}
              </Box>
            </Grid>
            <Grid item xs={12}>
              <Box display="flex" alignItems="center" gap={1}>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>Strategy Code</Typography>
                <Tooltip title="Paste or edit your strategy code here. Python only." arrow><HelpOutlineIcon fontSize="small" color="action" /></Tooltip>
              </Box>
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
              <Button variant="outlined" startIcon={<ContentCopyIcon />} sx={{ mb: 2, mr: 2 }} onClick={() => setPythonCode(strategyCode)} disabled={!strategyCode}>
                Clone from Selected
              </Button>
              <Button variant="outlined" startIcon={<ContentCopyIcon />} sx={{ mb: 2 }} onClick={() => setPythonCode('')}>Clear</Button>
            </Grid>
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
        <Box mb={2}>
          <Grid container spacing={2}>
            <Grid item xs={6} md={3}><Chip label={`Total Return: ${result.metrics?.totalReturn?.toFixed(2) ?? '--'}%`} color={result.metrics?.totalReturn > 0 ? 'success' : 'error'} /></Grid>
            <Grid item xs={6} md={3}><Chip label={`Annualized: ${result.metrics?.annualizedReturn?.toFixed(2) ?? '--'}%`} color={result.metrics?.annualizedReturn > 0 ? 'info' : 'default'} /></Grid>
            <Grid item xs={6} md={3}><Chip label={`Sharpe: ${result.metrics?.sharpeRatio?.toFixed(2) ?? '--'}`} color={result.metrics?.sharpeRatio > 1 ? 'primary' : 'warning'} /></Grid>
            <Grid item xs={6} md={3}><Chip label={`Max Drawdown: ${result.metrics?.maxDrawdown?.toFixed(2) ?? '--'}%`} color={result.metrics?.maxDrawdown < -10 ? 'error' : 'warning'} /></Grid>
            <Grid item xs={6} md={3}><Chip label={`Volatility: ${result.metrics?.volatility?.toFixed(2) ?? '--'}%`} color="default" /></Grid>
            <Grid item xs={6} md={3}><Chip label={`Win Rate: ${result.metrics?.winRate?.toFixed(2) ?? '--'}%`} color={result.metrics?.winRate > 50 ? 'success' : 'default'} /></Grid>
            <Grid item xs={6} md={3}><Chip label={`Profit Factor: ${result.metrics?.profitFactor?.toFixed(2) ?? '--'}`} color={result.metrics?.profitFactor > 1 ? 'success' : 'error'} /></Grid>
            <Grid item xs={6} md={3}><Chip label={`Trades: ${result.metrics?.totalTrades ?? '--'}`} color="secondary" /></Grid>
          </Grid>
        </Box>
      )}
      <Paper sx={{ p: 3, position: 'relative', minHeight: 400 }}>
        {(loading || isRunning) && (
          <Box sx={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', bgcolor: 'rgba(255,255,255,0.7)', zIndex: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <CircularProgress size={48} />
          </Box>
        )}
        {result && (
          <Tabs value={activeTab} onChange={(_, v) => setActiveTab(v)} sx={{ mb: 2 }}>
            <Tab label="Equity Curve" value="equity" />
            <Tab label="Drawdown" value="drawdown" />
            <Tab label="Trades" value="trades" />
            <Tab label="Logs" value="logs" />
            <Tab label="Summary" value="summary" />
            {result?.metrics?.custom && Object.keys(result.metrics.custom).length > 0 &&
              Object.keys(result.metrics.custom).map((k, i) => (
                <Tab key={k} label={`Metric: ${k}`} value={`custom_${k}`} />
              ))}
          </Tabs>
        )}
        {result && activeTab === 'equity' && result.equity && (
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
        {result && activeTab === 'drawdown' && result.equity && (
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
        {result && activeTab === 'trades' && result.trades && result.trades.length > 0 && (
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
        {result && activeTab === 'logs' && (
          <Box mt={2}>
            <Typography variant="subtitle2" color="text.secondary">Backtest Logs / Output</Typography>
            <Paper sx={{ p: 2, fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre', overflowX: 'auto', background: '#f7f7f7' }}>
              {logs}
            </Paper>
            <Button variant="outlined" startIcon={<DownloadIcon />} sx={{ mb: 2, mt: 2 }} onClick={handleDownloadLogs}>Download Logs</Button>
          </Box>
        )}
        {result && activeTab === 'summary' && result.metrics && (
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
        {result && (
          <Button variant="outlined" startIcon={<FileDownloadIcon />} sx={{ mb: 2, mr: 2 }} onClick={handleExport}>Export Results</Button>
        )}
        {result && (
          <Button variant="text" startIcon={<ContentCopyIcon />} sx={{ mb: 2, ml: 2 }} onClick={() => setShowApiExample(v => !v)}>
            {showApiExample ? 'Hide' : 'Show'} API Example
          </Button>
        )}
        {result && showApiExample && (
          <Paper sx={{ p: 2, fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre', overflowX: 'auto', background: '#f7f7f7', mb: 2 }}>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <span>Python API Example</span>
              <Button size="small" startIcon={<ContentCopyIcon />} onClick={handleCopyApiExample}>Copy</Button>
            </Box>
            {apiExample}
            <Box mt={2} />
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <span>cURL API Example</span>
              <Button size="small" startIcon={<ContentCopyIcon />} onClick={() => navigator.clipboard.writeText(curlExample)}>Copy</Button>
            </Box>
            {curlExample}
          </Paper>
        )}
        {activeTab.startsWith('custom_') && result?.metrics?.custom && (
          (() => {
            const metricKey = activeTab.replace('custom_', '');
            const metric = result.metrics.custom[metricKey];
            if (!metric) return null;
            return (
              <Box mb={2}>
                <Typography variant="subtitle2">Custom Metric: {metricKey}</Typography>
                <Line
                  data={{
                    labels: metric.map(p => p.date || p[0]),
                    datasets: [{
                      label: metricKey,
                      data: metric.map(p => p.value ?? p[1]),
                      borderColor: '#8e24aa',
                      fill: false,
                      pointRadius: 0
                    }]
                  }}
                  options={{
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: { x: { display: false } }
                  }}
                />
              </Box>
            );
          })()
        )}
      </Paper>
      {batchQueue.length > 0 && (
        <Card sx={{ mt: 4 }}>
          <CardContent>
            <Typography variant="h6">Batch Run Progress</Typography>
            <Box sx={{ width: '100%', mb: 2 }}>
              <LinearProgress variant="determinate" value={batchProgress * 100} />
              <Typography variant="body2">{Math.round(batchProgress * 100)}% complete</Typography>
            </Box>
            <Button variant="outlined" color="error" onClick={handleBatchCancel} disabled={!batchRunning}>Cancel Batch</Button>
            <TableContainer component={Paper} sx={{ mt: 2 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Params</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Result</TableCell>
                    <TableCell>Error</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {batchQueue.map((item, i) => (
                    <TableRow key={i}>
                      <TableCell>{JSON.stringify(item.params)}</TableCell>
                      <TableCell>{item.status}</TableCell>
                      <TableCell>{item.result ? '✅' : ''}</TableCell>
                      <TableCell>{item.error}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <Button variant="outlined" sx={{ mt: 2 }} onClick={() => {
              // Export all batch results as CSV
              const rows = batchQueue.filter(b => b.result).map(b => ({ ...b.params, ...b.result.metrics }));
              const header = Object.keys(rows[0] || {}).join(',');
              const csv = [header, ...rows.map(r => Object.values(r).join(','))].join('\n');
              const blob = new Blob([csv], { type: 'text/csv' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'batch_results.csv';
              a.click();
              URL.revokeObjectURL(url);
            }}>Export All Results (CSV)</Button>
          </CardContent>
        </Card>
      )}
      {result && (
        <Box mb={2}>
          <Typography variant="subtitle2">Advanced Metrics</Typography>
          <Grid container spacing={2}>
            {Object.entries(getAdvancedMetrics(result)).map(([k, v]) => (
              <Grid item key={k}><Chip label={`${k}: ${v !== null && v !== undefined ? v.toFixed(3) : '--'}`} color="info" /></Grid>
            ))}
          </Grid>
        </Box>
      )}
      <Card sx={{ mt: 4 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Saved Strategies</Typography>
          <TableContainer component={Paper} sx={{ mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Actions</TableCell>
                  <TableCell>History</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {savedStrategies.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>{s.name}</TableCell>
                    <TableCell>
                      <Button size="small" onClick={() => handleLoadStrategy(s.code)}>Load</Button>
                      <Button size="small" onClick={() => handleRenameStrategy(s.id)}>Rename</Button>
                      <Button size="small" onClick={() => { setPythonCode(s.code); setUseCustomCode(true); }}>Clone</Button>
                      <Button size="small" color="error" onClick={() => handleDeleteStrategy(s.id)}>Delete</Button>
                    </TableCell>
                    <TableCell>
                      <Button size="small" onClick={() => alert(JSON.stringify(strategyHistory[s.id] || [], null, 2))}>Show Versions</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
      <Box sx={{ mb: 4 }}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" gap={1} mb={2}>
              <Typography variant="h6">Parameter Sweep</Typography>
              <Tooltip title="Run a grid search over parameter values. Use comma-separated lists (e.g. 10,20,30) or range (e.g. 10-30:5 for 10,15,20,25,30)." arrow>
                <HelpOutlineIcon fontSize="small" color="action" />
              </Tooltip>
            </Box>
            <Grid container spacing={2}>
              {paramConfig.map(param => (
                <Grid item key={param.name} xs={12} sm={4} md={3}>
                  <Tooltip title={param.label} arrow>
                    <TextField
                      label={param.label}
                      value={sweepParams[param.name] ?? ''}
                      onChange={e => handleSweepParamChange(param.name, e.target.value)}
                      size="small"
                      fullWidth
                      placeholder={String(param.default)}
                      helperText="List: 10,20,30 or Range: 10-30:5"
                    />
                  </Tooltip>
                </Grid>
              ))}
            </Grid>
            <Box mt={2} display="flex" alignItems="center" gap={2}>
              <Button variant="contained" color="primary" onClick={handleRunSweep} disabled={sweepRunning || !paramConfig.length}>Run Sweep</Button>
              <Button variant="outlined" color="error" onClick={handleStopSweep} disabled={!sweepRunning}>Stop</Button>
              {sweepRunning && <Typography variant="body2">Progress: {sweepProgress.current} / {sweepProgress.total}</Typography>}
            </Box>
            {sweepResults.length > 0 && (
              <Box mt={3}>
                <Typography variant="subtitle2">Sweep Results</Typography>
                <TableContainer component={Paper} sx={{ mb: 2 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        {paramConfig.map(p => <TableCell key={p.name}>{p.label}</TableCell>)}
                        <TableCell>Total Return</TableCell>
                        <TableCell>Sharpe</TableCell>
                        <TableCell>Max Drawdown</TableCell>
                        <TableCell>Success</TableCell>
                        <TableCell>Error</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {sweepResults.map((r, i) => (
                        <TableRow key={i} sx={{ bgcolor: r.success ? undefined : '#ffebee' }}>
                          {paramConfig.map(p => <TableCell key={p.name}>{r.params[p.name]}</TableCell>)}
                          <TableCell>{r.metrics?.totalReturn?.toFixed(2) ?? '--'}</TableCell>
                          <TableCell>{r.metrics?.sharpeRatio?.toFixed(2) ?? '--'}</TableCell>
                          <TableCell>{r.metrics?.maxDrawdown?.toFixed(2) ?? '--'}</TableCell>
                          <TableCell>{r.success ? 'Yes' : 'No'}</TableCell>
                          <TableCell sx={{ maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.error || ''}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                <Button variant="outlined" startIcon={<FileDownloadIcon />} onClick={() => {
                  const csv = [
                    [...paramConfig.map(p => p.label), 'Total Return', 'Sharpe', 'Max Drawdown', 'Success', 'Error'].join(','),
                    ...sweepResults.map(r => [
                      ...paramConfig.map(p => r.params[p.name]),
                      r.metrics?.totalReturn ?? '',
                      r.metrics?.sharpeRatio ?? '',
                      r.metrics?.maxDrawdown ?? '',
                      r.success ? 'Yes' : 'No',
                      r.error ? '"' + r.error.replace(/"/g, '""') + '"' : ''
                    ].join(','))
                  ].join('\n');
                  const blob = new Blob([csv], { type: 'text/csv' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `sweep_results_${params.symbol}_${params.strategy}.csv`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}>Export Sweep Results (CSV)</Button>
              </Box>
            )}
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
}
