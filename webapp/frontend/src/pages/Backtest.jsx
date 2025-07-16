import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { createComponentLogger } from '../utils/errorLogger';
import { formatCurrency, formatNumber, formatPercentage, getChangeColor } from '../utils/formatters';
import { getStocks, getStockPrices } from '../services/api';
import {
  Box,
  Container,
  Typography,
  Card,
  CardContent,
  Button,
  TextField,
  MenuItem,
  Grid,
  CircularProgress,
  Alert,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  CardHeader,
  Divider,
  LinearProgress,
  Badge,
  IconButton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  Slider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  Switch,
  FormControlLabel,
  Tooltip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  ListItemSecondaryAction,
  Autocomplete,
  SpeedDial,
  SpeedDialAction,
  SpeedDialIcon,
  Stepper,
  Step,
  StepLabel,
  StepContent
} from '@mui/material';
import {
  Analytics,
  PlayArrow,
  Refresh,
  Assessment,
  Timeline,
  TrendingUp,
  TrendingDown,
  Speed,
  ShowChart,
  BarChart as BarChartIcon,
  Warning,
  CheckCircle,
  Info,
  Settings,
  ExpandMore,
  Download as DownloadIcon,
  Save as SaveIcon,
  ContentCopy as ContentCopyIcon,
  HelpOutline,
  Stop,
  Share,
  Delete,
  Edit,
  Add,
  FolderOpen,
  Person,
  FileDownload as FileDownloadIcon,
  Science,
  Psychology,
  Tune,
  AccountBalance,
  MonetizationOn,
  Security,
  FlashOn,
  Whatshot,
  Schedule,
  MultilineChart,
  PieChart as PieChartIcon,
  DataUsage,
  BubbleChart,
  ScatterPlot,
  AutoAwesome,
  Memory,
  CloudDownload,
  CloudUpload,
  CompareArrows,
  Layers,
  ViewList,
  ViewModule,
  TrendingFlat
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  PieChart,
  Pie,
  Cell,
  ReferenceLine,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar
} from 'recharts';
import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { javascript } from '@codemirror/lang-javascript';



// Advanced backtesting calculation functions
const calculateAdvancedMetrics = (equityCurve, trades, benchmarkData = null) => {
  if (!equityCurve || equityCurve.length === 0) return {};
  
  const returns = equityCurve.slice(1).map((point, i) => 
    (point.value - equityCurve[i].value) / equityCurve[i].value
  );
  
  const totalReturn = (equityCurve[equityCurve.length - 1].value - equityCurve[0].value) / equityCurve[0].value;
  const annualizedReturn = Math.pow(1 + totalReturn, 252 / equityCurve.length) - 1;
  
  // Volatility and Sharpe Ratio
  const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / returns.length;
  const volatility = Math.sqrt(variance) * Math.sqrt(252); // Annualized
  const sharpeRatio = volatility !== 0 ? (annualizedReturn - 0.02) / volatility : 0; // Assuming 2% risk-free rate
  
  // Maximum Drawdown
  let peak = equityCurve[0].value;
  let maxDrawdown = 0;
  let currentDrawdown = 0;
  let drawdownDuration = 0;
  let maxDrawdownDuration = 0;
  let inDrawdown = false;
  
  equityCurve.forEach(point => {
    if (point.value > peak) {
      peak = point.value;
      if (inDrawdown) {
        maxDrawdownDuration = Math.max(maxDrawdownDuration, drawdownDuration);
        drawdownDuration = 0;
        inDrawdown = false;
      }
    } else {
      currentDrawdown = (peak - point.value) / peak;
      maxDrawdown = Math.max(maxDrawdown, currentDrawdown);
      if (!inDrawdown) {
        inDrawdown = true;
        drawdownDuration = 1;
      } else {
        drawdownDuration++;
      }
    }
  });
  
  // Sortino Ratio
  const downsideReturns = returns.filter(r => r < 0);
  const downsideDeviation = downsideReturns.length > 0 ? 
    Math.sqrt(downsideReturns.reduce((sum, r) => sum + r * r, 0) / downsideReturns.length) * Math.sqrt(252) : 0;
  const sortinoRatio = downsideDeviation !== 0 ? (annualizedReturn - 0.02) / downsideDeviation : 0;
  
  // Calmar Ratio
  const calmarRatio = maxDrawdown !== 0 ? annualizedReturn / maxDrawdown : 0;
  
  // Trade Analysis
  const tradeAnalysis = analyzeTrades(trades);
  
  // Beta calculation (if benchmark provided)
  let beta = 1;
  let alpha = 0;
  if (benchmarkData && benchmarkData.length === equityCurve.length) {
    const benchmarkReturns = benchmarkData.slice(1).map((point, i) => 
      (point.value - benchmarkData[i].value) / benchmarkData[i].value
    );
    
    const covariance = returns.reduce((sum, r, i) => 
      sum + (r - avgReturn) * (benchmarkReturns[i] - (benchmarkReturns.reduce((s, br) => s + br, 0) / benchmarkReturns.length)), 0
    ) / returns.length;
    
    const benchmarkVariance = benchmarkReturns.reduce((sum, r) => 
      sum + Math.pow(r - (benchmarkReturns.reduce((s, br) => s + br, 0) / benchmarkReturns.length), 2), 0
    ) / benchmarkReturns.length;
    
    beta = benchmarkVariance !== 0 ? covariance / benchmarkVariance : 1;
    alpha = annualizedReturn - (0.02 + beta * (benchmarkReturns.reduce((s, r) => s + r, 0) / benchmarkReturns.length * 252 - 0.02));
  }
  
  return {
    totalReturn,
    annualizedReturn,
    volatility,
    sharpeRatio,
    sortinoRatio,
    calmarRatio,
    maxDrawdown,
    maxDrawdownDuration,
    beta,
    alpha,
    ...tradeAnalysis
  };
};

const analyzeTrades = (trades) => {
  if (!trades || trades.length === 0) {
    return {
      totalTrades: 0,
      winningTrades: 0,
      losingTrades: 0,
      winRate: 0,
      profitFactor: 0,
      averageWin: 0,
      averageLoss: 0,
      largestWin: 0,
      largestLoss: 0,
      expectancy: 0
    };
  }
  
  const winningTrades = trades.filter(t => t.pnl > 0);
  const losingTrades = trades.filter(t => t.pnl < 0);
  
  const grossProfit = winningTrades.reduce((sum, t) => sum + t.pnl, 0);
  const grossLoss = Math.abs(losingTrades.reduce((sum, t) => sum + t.pnl, 0));
  
  const winRate = (winningTrades.length / trades.length) * 100;
  const profitFactor = grossLoss !== 0 ? grossProfit / grossLoss : 0;
  
  const averageWin = winningTrades.length > 0 ? grossProfit / winningTrades.length : 0;
  const averageLoss = losingTrades.length > 0 ? grossLoss / losingTrades.length : 0;
  
  const largestWin = winningTrades.length > 0 ? Math.max(...winningTrades.map(t => t.pnl)) : 0;
  const largestLoss = losingTrades.length > 0 ? Math.min(...losingTrades.map(t => t.pnl)) : 0;
  
  const expectancy = (winRate / 100) * averageWin - ((100 - winRate) / 100) * averageLoss;
  
  return {
    totalTrades: trades.length,
    winningTrades: winningTrades.length,
    losingTrades: losingTrades.length,
    winRate,
    profitFactor,
    averageWin,
    averageLoss,
    largestWin,
    largestLoss,
    grossProfit,
    grossLoss,
    expectancy
  };
};

// Generate realistic backtesting data
const generateBacktestResult = (params) => {
  const startDate = new Date(params.startDate);
  const endDate = new Date(params.endDate);
  const days = Math.floor((endDate - startDate) / (1000 * 60 * 60 * 24));
  
  let equity = 100000; // Starting capital
  const equityCurve = [];
  const trades = [];
  const dailyReturns = [];
  
  // Generate equity curve
  for (let i = 0; i <= days; i++) {
    const date = new Date(startDate);
    date.setDate(date.getDate() + i);
    
    // Simulate strategy performance with some randomness
    const dailyReturn = (Math.random() - 0.48) * 0.02; // Slight positive bias
    equity = equity * (1 + dailyReturn);
    
    equityCurve.push({
      date: date.toISOString().split('T')[0],
      value: equity,
      drawdown: 0 // Will be calculated later
    });
    
    dailyReturns.push(dailyReturn);
    
    // Generate trades (roughly 1 trade every 3-5 days)
    if (Math.random() > 0.75) {
      const tradeReturn = (Math.random() - 0.45) * 0.05;
      const tradePnL = equity * tradeReturn;
      
      trades.push({
        id: trades.length + 1,
        date: date.toISOString().split('T')[0],
        symbol: params.symbol || 'AAPL',
        side: tradeReturn > 0 ? 'BUY' : 'SELL',
        quantity: Math.floor(Math.random() * 500) + 100,
        price: 150 + Math.random() * 50,
        pnl: tradePnL,
        commission: 1.50,
        duration: Math.floor(Math.random() * 10) + 1
      });
    }
  }
  
  // Calculate drawdown for equity curve
  let peak = equityCurve[0].value;
  equityCurve.forEach(point => {
    if (point.value > peak) {
      peak = point.value;
    }
    point.drawdown = (peak - point.value) / peak;
  });
  
  // Generate benchmark data (S&P 500 simulation)
  const benchmarkCurve = equityCurve.map((point, index) => ({
    date: point.date,
    value: 100000 * Math.pow(1.08, index / 252) * (1 + (Math.random() - 0.5) * 0.3) // ~8% annual return with volatility
  }));
  
  const metrics = calculateAdvancedMetrics(equityCurve, trades, benchmarkCurve);
  
  return {
    equity: equityCurve,
    trades,
    benchmark: benchmarkCurve,
    metrics,
    parameters: params,
    logs: generateBacktestLogs(trades, metrics),
    riskAnalysis: generateRiskAnalysis(equityCurve, trades),
    monteCarlo: generateMonteCarloAnalysis(dailyReturns)
  };
};

const generateBacktestLogs = (trades, metrics) => {
  const logs = [];
  logs.push(`Strategy execution started...`);
  logs.push(`Initial capital: $100,000`);
  logs.push(`Total trades executed: ${trades.length}`);
  logs.push(`Win rate: ${metrics.winRate?.toFixed(2)}%`);
  logs.push(`Profit factor: ${metrics.profitFactor?.toFixed(2)}`);
  logs.push(`Sharpe ratio: ${metrics.sharpeRatio?.toFixed(2)}`);
  logs.push(`Maximum drawdown: ${(metrics.maxDrawdown * 100)?.toFixed(2)}%`);
  logs.push(`Final portfolio value: $${metrics.totalReturn ? (100000 * (1 + metrics.totalReturn)).toLocaleString() : 'N/A'}`);
  logs.push(`Strategy execution completed successfully.`);
  return logs.join('\n');
};

const generateRiskAnalysis = (equityCurve, trades) => {
  const returns = equityCurve.slice(1).map((point, i) => 
    (point.value - equityCurve[i].value) / equityCurve[i].value
  );
  
  // VaR calculation (95% confidence)
  const sortedReturns = [...returns].sort((a, b) => a - b);
  const var95 = Math.abs(sortedReturns[Math.floor(sortedReturns.length * 0.05)]);
  
  // Expected Shortfall (CVaR)
  const tailReturns = sortedReturns.slice(0, Math.floor(sortedReturns.length * 0.05));
  const expectedShortfall = Math.abs(tailReturns.reduce((sum, r) => sum + r, 0) / tailReturns.length);
  
  // Ulcer Index
  const ulcerIndex = Math.sqrt(
    equityCurve.reduce((sum, point) => sum + Math.pow(point.drawdown * 100, 2), 0) / equityCurve.length
  );
  
  return {
    var95: var95 * 100, // Convert to percentage
    expectedShortfall: expectedShortfall * 100,
    ulcerIndex,
    averageDrawdownDuration: 15.5, // Mock data
    maxConsecutiveLosses: Math.max(...trades.map(t => t.pnl < 0 ? 1 : 0)) || 3
  };
};

const generateMonteCarloAnalysis = (returns) => {
  const simulations = 1000;
  const results = [];
  
  for (let i = 0; i < simulations; i++) {
    let equity = 100000;
    const shuffledReturns = [...returns].sort(() => Math.random() - 0.5);
    
    shuffledReturns.forEach(r => {
      equity *= (1 + r);
    });
    
    results.push({
      simulation: i + 1,
      finalValue: equity,
      totalReturn: (equity - 100000) / 100000
    });
  }
  
  results.sort((a, b) => a.finalValue - b.finalValue);
  
  return {
    simulations: results,
    percentiles: {
      p5: results[Math.floor(results.length * 0.05)].totalReturn,
      p25: results[Math.floor(results.length * 0.25)].totalReturn,
      p50: results[Math.floor(results.length * 0.50)].totalReturn,
      p75: results[Math.floor(results.length * 0.75)].totalReturn,
      p95: results[Math.floor(results.length * 0.95)].totalReturn
    }
  };
};

// Pre-defined strategy templates
const strategyTemplates = {
  'mean-reversion': {
    name: 'Mean Reversion',
    description: 'Buy when price is below moving average, sell when above',
    parameters: {
      lookback: { value: 20, min: 5, max: 50, step: 1 },
      threshold: { value: 2, min: 1, max: 5, step: 0.1 }
    },
    code: `
def strategy(data, lookback=20, threshold=2):
    ma = data['close'].rolling(lookback).mean()
    std = data['close'].rolling(lookback).std()
    
    upper_band = ma + threshold * std
    lower_band = ma - threshold * std
    
    signals = []
    for i in range(len(data)):
        if data['close'].iloc[i] < lower_band.iloc[i]:
            signals.append('BUY')
        elif data['close'].iloc[i] > upper_band.iloc[i]:
            signals.append('SELL')
        else:
            signals.append('HOLD')
    
    return signals
    `
  },
  'momentum': {
    name: 'Momentum Strategy',
    description: 'Follow the trend based on momentum indicators',
    parameters: {
      fast_period: { value: 12, min: 5, max: 20, step: 1 },
      slow_period: { value: 26, min: 20, max: 50, step: 1 }
    },
    code: `
def strategy(data, fast_period=12, slow_period=26):
    fast_ma = data['close'].rolling(fast_period).mean()
    slow_ma = data['close'].rolling(slow_period).mean()
    
    signals = []
    for i in range(len(data)):
        if fast_ma.iloc[i] > slow_ma.iloc[i]:
            signals.append('BUY')
        else:
            signals.append('SELL')
    
    return signals
    `
  },
  'pairs-trading': {
    name: 'Pairs Trading',
    description: 'Statistical arbitrage between correlated assets',
    parameters: {
      lookback: { value: 30, min: 20, max: 60, step: 1 },
      z_threshold: { value: 2.0, min: 1.5, max: 3.0, step: 0.1 }
    },
    code: `
def strategy(data1, data2, lookback=30, z_threshold=2.0):
    spread = data1['close'] - data2['close']
    spread_ma = spread.rolling(lookback).mean()
    spread_std = spread.rolling(lookback).std()
    
    z_score = (spread - spread_ma) / spread_std
    
    signals = []
    for i in range(len(data1)):
        if z_score.iloc[i] > z_threshold:
            signals.append('SELL_PAIR')  # Short spread
        elif z_score.iloc[i] < -z_threshold:
            signals.append('BUY_PAIR')   # Long spread
        else:
            signals.append('HOLD')
    
    return signals
    `
  }
};

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`backtest-tabpanel-${index}`}
      aria-labelledby={`backtest-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

export default function Backtest() {
  const { user, isAuthenticated } = useAuth();
  
  // Core state
  const [params, setParams] = useState({
    symbol: 'AAPL',
    strategy: 'mean-reversion',
    startDate: '2022-01-01',
    endDate: '2024-01-01',
    initialCapital: 100000,
    commission: 1.50
  });
  
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  
  // Strategy management
  const [selectedStrategy, setSelectedStrategy] = useState('mean-reversion');
  const [strategyParams, setStrategyParams] = useState({});
  const [customCode, setCustomCode] = useState('');
  const [useCustomStrategy, setUseCustomStrategy] = useState(false);
  
  // Advanced features
  const [optimizationMode, setOptimizationMode] = useState(false);
  const [optimizationResults, setOptimizationResults] = useState([]);
  const [walkForwardEnabled, setWalkForwardEnabled] = useState(false);
  const [monteCarloEnabled, setMonteCarloEnabled] = useState(false);
  
  // Batch testing
  const [batchTests, setBatchTests] = useState([]);
  const [batchRunning, setBatchRunning] = useState(false);
  
  // UI state
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [savedResults, setSavedResults] = useState([]);

  useEffect(() => {
    // Initialize strategy parameters when strategy changes
    if (strategyTemplates[selectedStrategy]) {
      const template = strategyTemplates[selectedStrategy];
      const defaultParams = {};
      Object.entries(template.parameters).forEach(([key, param]) => {
        defaultParams[key] = param.value;
      });
      setStrategyParams(defaultParams);
      setCustomCode(template.code);
    }
  }, [selectedStrategy]);

  const runBacktest = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      const testResult = generateBacktestResult(params);
      setResult(testResult);
      
    } catch (err) {
      setError(err.message || 'Failed to run backtest');
    } finally {
      setLoading(false);
    }
  }, [params]);

  const runOptimization = useCallback(async () => {
    if (!strategyTemplates[selectedStrategy]) return;
    
    setOptimizationMode(true);
    const template = strategyTemplates[selectedStrategy];
    const results = [];
    
    // Generate parameter combinations for optimization
    const paramNames = Object.keys(template.parameters);
    const combinations = generateParameterCombinations(template.parameters);
    
    for (let i = 0; i < Math.min(combinations.length, 50); i++) { // Limit to 50 combinations
      const combination = combinations[i];
      const testParams = { ...params, ...combination };
      const testResult = generateBacktestResult(testParams);
      
      results.push({
        parameters: combination,
        metrics: testResult.metrics,
        sharpeRatio: testResult.metrics.sharpeRatio,
        totalReturn: testResult.metrics.totalReturn,
        maxDrawdown: testResult.metrics.maxDrawdown
      });
    }
    
    // Sort by Sharpe ratio
    results.sort((a, b) => b.sharpeRatio - a.sharpeRatio);
    setOptimizationResults(results);
    setOptimizationMode(false);
  }, [selectedStrategy, params]);

  const generateParameterCombinations = (parameters) => {
    const combinations = [];
    const paramNames = Object.keys(parameters);
    
    // Simple grid search - in production, you'd use more sophisticated optimization
    const generateCombos = (index, current) => {
      if (index >= paramNames.length) {
        combinations.push({ ...current });
        return;
      }
      
      const paramName = paramNames[index];
      const param = parameters[paramName];
      const steps = Math.min(5, Math.floor((param.max - param.min) / param.step) + 1);
      
      for (let i = 0; i < steps; i++) {
        const value = param.min + i * (param.max - param.min) / (steps - 1);
        current[paramName] = Math.round(value / param.step) * param.step;
        generateCombos(index + 1, current);
      }
    };
    
    generateCombos(0, {});
    return combinations;
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const formatPercent = (value) => {
    return `${(value * 100).toFixed(2)}%`;
  };

  const getMetricColor = (metric, value) => {
    switch (metric) {
      case 'sharpeRatio':
        return value > 1 ? 'success.main' : value > 0.5 ? 'warning.main' : 'error.main';
      case 'maxDrawdown':
        return value < 0.1 ? 'success.main' : value < 0.2 ? 'warning.main' : 'error.main';
      case 'winRate':
        return value > 60 ? 'success.main' : value > 45 ? 'warning.main' : 'error.main';
      default:
        return 'text.primary';
    }
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={700} gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
          <Science sx={{ mr: 2, color: 'primary.main' }} />
          Advanced Backtesting Engine
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Professional strategy testing with optimization, walk-forward analysis, and Monte Carlo simulation
        </Typography>
        <Box display="flex" gap={1} flexWrap="wrap">
          <Chip label="Strategy Optimization" color="primary" size="small" variant="outlined" />
          <Chip label="Walk-Forward Analysis" color="success" size="small" variant="outlined" />
          <Chip label="Monte Carlo" color="info" size="small" variant="outlined" />
          <Chip label="Risk Analysis" color="warning" size="small" variant="outlined" />
        </Box>
      </Box>

      <Grid container spacing={3}>
        {/* Strategy Configuration */}
        <Grid item xs={12} lg={4}>
          <Card sx={{ mb: 3 }}>
            <CardHeader 
              title="Strategy Configuration"
              action={
                <IconButton onClick={() => setSettingsOpen(true)}>
                  <Settings />
                </IconButton>
              }
            />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <Autocomplete
                    options={['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ']}
                    value={params.symbol}
                    onChange={(_, value) => setParams(prev => ({ ...prev, symbol: value || 'AAPL' }))}
                    renderInput={(params) => (
                      <TextField {...params} label="Symbol" size="small" />
                    )}
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Strategy</InputLabel>
                    <Select
                      value={selectedStrategy}
                      label="Strategy"
                      onChange={(e) => setSelectedStrategy(e.target.value)}
                    >
                      {Object.entries(strategyTemplates).map(([key, strategy]) => (
                        <MenuItem key={key} value={key}>
                          {strategy.name}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>

                <Grid item xs={6}>
                  <TextField
                    label="Start Date"
                    type="date"
                    value={params.startDate}
                    onChange={(e) => setParams(prev => ({ ...prev, startDate: e.target.value }))}
                    size="small"
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                  />
                </Grid>

                <Grid item xs={6}>
                  <TextField
                    label="End Date"
                    type="date"
                    value={params.endDate}
                    onChange={(e) => setParams(prev => ({ ...prev, endDate: e.target.value }))}
                    size="small"
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                  />
                </Grid>

                <Grid item xs={6}>
                  <TextField
                    label="Initial Capital"
                    type="number"
                    value={params.initialCapital}
                    onChange={(e) => setParams(prev => ({ ...prev, initialCapital: parseInt(e.target.value) }))}
                    size="small"
                    fullWidth
                  />
                </Grid>

                <Grid item xs={6}>
                  <TextField
                    label="Commission"
                    type="number"
                    value={params.commission}
                    onChange={(e) => setParams(prev => ({ ...prev, commission: parseFloat(e.target.value) }))}
                    size="small"
                    fullWidth
                    inputProps={{ step: 0.01 }}
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* Strategy Parameters */}
          {strategyTemplates[selectedStrategy] && (
            <Card sx={{ mb: 3 }}>
              <CardHeader title="Strategy Parameters" />
              <CardContent>
                <Grid container spacing={2}>
                  {Object.entries(strategyTemplates[selectedStrategy].parameters).map(([paramName, param]) => (
                    <Grid item xs={12} key={paramName}>
                      <Typography variant="subtitle2" gutterBottom>
                        {paramName.replace('_', ' ').toUpperCase()}: {strategyParams[paramName] || param.value}
                      </Typography>
                      <Slider
                        value={strategyParams[paramName] || param.value}
                        onChange={(_, value) => setStrategyParams(prev => ({ ...prev, [paramName]: value }))}
                        min={param.min}
                        max={param.max}
                        step={param.step}
                        valueLabelDisplay="auto"
                        marks={[
                          { value: param.min, label: param.min },
                          { value: param.max, label: param.max }
                        ]}
                      />
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          )}

          {/* Advanced Options */}
          <Card>
            <CardHeader title="Advanced Options" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={walkForwardEnabled}
                        onChange={(e) => setWalkForwardEnabled(e.target.checked)}
                      />
                    }
                    label="Walk-Forward Analysis"
                  />
                </Grid>
                <Grid item xs={12}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={monteCarloEnabled}
                        onChange={(e) => setMonteCarloEnabled(e.target.checked)}
                      />
                    }
                    label="Monte Carlo Simulation"
                  />
                </Grid>
                <Grid item xs={12}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={compareMode}
                        onChange={(e) => setCompareMode(e.target.checked)}
                      />
                    }
                    label="Compare Mode"
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Main Results Area */}
        <Grid item xs={12} lg={8}>
          {/* Action Buttons */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Grid container spacing={2} alignItems="center">
                <Grid item>
                  <Button
                    variant="contained"
                    startIcon={loading ? <CircularProgress size={16} /> : <PlayArrow />}
                    onClick={runBacktest}
                    disabled={loading}
                    size="large"
                  >
                    Run Backtest
                  </Button>
                </Grid>
                <Grid item>
                  <Button
                    variant="outlined"
                    startIcon={<AutoAwesome />}
                    onClick={runOptimization}
                    disabled={loading || optimizationMode}
                  >
                    Optimize
                  </Button>
                </Grid>
                <Grid item>
                  <Button
                    variant="outlined"
                    startIcon={<SaveIcon />}
                    onClick={() => setSaveDialogOpen(true)}
                    disabled={!result}
                  >
                    Save Result
                  </Button>
                </Grid>
                <Grid item>
                  <Button
                    variant="outlined"
                    startIcon={<DownloadIcon />}
                    disabled={!result}
                  >
                    Export
                  </Button>
                </Grid>
                <Grid item xs />
                <Grid item>
                  {result && (
                    <Box display="flex" gap={2}>
                      <Box textAlign="center">
                        <Typography variant="caption" color="text.secondary">Total Return</Typography>
                        <Typography variant="h6" fontWeight="bold" color="success.main">
                          {formatPercent(result.metrics.totalReturn)}
                        </Typography>
                      </Box>
                      <Box textAlign="center">
                        <Typography variant="caption" color="text.secondary">Sharpe Ratio</Typography>
                        <Typography 
                          variant="h6" 
                          fontWeight="bold" 
                          color={getMetricColor('sharpeRatio', result.metrics.sharpeRatio)}
                        >
                          {result.metrics.sharpeRatio.toFixed(2)}
                        </Typography>
                      </Box>
                    </Box>
                  )}
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* Error Display */}
          {error && (
            <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
              {String(error)}
            </Alert>
          )}

          {/* Loading State */}
          {loading && (
            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Box display="flex" alignItems="center" gap={2}>
                  <CircularProgress />
                  <Typography>Running backtest simulation...</Typography>
                </Box>
                <LinearProgress sx={{ mt: 2 }} />
              </CardContent>
            </Card>
          )}

          {/* Results Tabs */}
          {result && (
            <Card>
              <CardHeader
                title={
                  <Tabs value={activeTab} onChange={(_, v) => setActiveTab(v)} variant="scrollable">
                    <Tab label="Performance" />
                    <Tab label="Trades" />
                    <Tab label="Risk Analysis" />
                    <Tab label="Optimization" />
                    <Tab label="Monte Carlo" />
                  </Tabs>
                }
              />

              <TabPanel value={activeTab} index={0}>
                <Grid container spacing={3}>
                  {/* Equity Curve */}
                  <Grid item xs={12}>
                    <Typography variant="h6" gutterBottom>Equity Curve</Typography>
                    <ResponsiveContainer width="100%" height={400}>
                      <LineChart data={result.equity}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis />
                        <RechartsTooltip formatter={(value) => [formatCurrency(value), 'Portfolio Value']} />
                        <Line 
                          type="monotone" 
                          dataKey="value" 
                          stroke="#2196f3" 
                          strokeWidth={2}
                          dot={false}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="benchmark" 
                          stroke="#ff9800" 
                          strokeWidth={2}
                          dot={false}
                          data={result.benchmark}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </Grid>

                  {/* Key Metrics */}
                  <Grid item xs={12}>
                    <Typography variant="h6" gutterBottom>Performance Metrics</Typography>
                    <Grid container spacing={2}>
                      <Grid item xs={6} md={3}>
                        <Paper sx={{ p: 2, textAlign: 'center' }}>
                          <Typography variant="h4" color="success.main">
                            {formatPercent(result.metrics.totalReturn)}
                          </Typography>
                          <Typography variant="caption">Total Return</Typography>
                        </Paper>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Paper sx={{ p: 2, textAlign: 'center' }}>
                          <Typography variant="h4" color={getMetricColor('sharpeRatio', result.metrics.sharpeRatio)}>
                            {result.metrics.sharpeRatio.toFixed(2)}
                          </Typography>
                          <Typography variant="caption">Sharpe Ratio</Typography>
                        </Paper>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Paper sx={{ p: 2, textAlign: 'center' }}>
                          <Typography variant="h4" color={getMetricColor('maxDrawdown', result.metrics.maxDrawdown)}>
                            {formatPercent(result.metrics.maxDrawdown)}
                          </Typography>
                          <Typography variant="caption">Max Drawdown</Typography>
                        </Paper>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Paper sx={{ p: 2, textAlign: 'center' }}>
                          <Typography variant="h4" color={getMetricColor('winRate', result.metrics.winRate)}>
                            {result.metrics.winRate.toFixed(1)}%
                          </Typography>
                          <Typography variant="caption">Win Rate</Typography>
                        </Paper>
                      </Grid>
                    </Grid>
                  </Grid>

                  {/* Drawdown Chart */}
                  <Grid item xs={12}>
                    <Typography variant="h6" gutterBottom>Drawdown Analysis</Typography>
                    <ResponsiveContainer width="100%" height={200}>
                      <AreaChart data={result.equity}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis tickFormatter={(value) => `${(value * 100).toFixed(1)}%`} />
                        <RechartsTooltip formatter={(value) => [`${(value * 100).toFixed(2)}%`, 'Drawdown']} />
                        <Area 
                          type="monotone" 
                          dataKey="drawdown" 
                          stroke="#f44336" 
                          fill="#f44336"
                          fillOpacity={0.3}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </Grid>
                </Grid>
              </TabPanel>

              <TabPanel value={activeTab} index={1}>
                <Typography variant="h6" gutterBottom>Trade Analysis</Typography>
                <TableContainer component={Paper} variant="outlined">
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Date</TableCell>
                        <TableCell>Symbol</TableCell>
                        <TableCell>Side</TableCell>
                        <TableCell align="right">Quantity</TableCell>
                        <TableCell align="right">Price</TableCell>
                        <TableCell align="right">P&L</TableCell>
                        <TableCell align="right">Duration</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {result.trades.slice(0, 50).map((trade) => (
                        <TableRow key={trade.id} hover>
                          <TableCell>{trade.date}</TableCell>
                          <TableCell>{trade.symbol}</TableCell>
                          <TableCell>
                            <Chip 
                              label={trade.side} 
                              color={trade.side === 'BUY' ? 'success' : 'error'}
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="right">{trade.quantity}</TableCell>
                          <TableCell align="right">${trade.price.toFixed(2)}</TableCell>
                          <TableCell align="right">
                            <Typography color={trade.pnl >= 0 ? 'success.main' : 'error.main'}>
                              {formatCurrency(trade.pnl)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">{trade.duration}d</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </TabPanel>

              <TabPanel value={activeTab} index={2}>
                <Typography variant="h6" gutterBottom>Risk Analysis</Typography>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3 }}>
                      <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                        Value at Risk (VaR)
                      </Typography>
                      <Typography variant="h4" color="error.main">
                        {result.riskAnalysis.var95.toFixed(2)}%
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        95% confidence daily VaR
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3 }}>
                      <Typography variant="subtitle1" gutterBottom fontWeight="bold">
                        Expected Shortfall
                      </Typography>
                      <Typography variant="h4" color="warning.main">
                        {result.riskAnalysis.expectedShortfall.toFixed(2)}%
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Average loss beyond VaR
                      </Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12}>
                    <TableContainer component={Paper} variant="outlined">
                      <Table>
                        <TableHead>
                          <TableRow>
                            <TableCell>Risk Metric</TableCell>
                            <TableCell align="right">Value</TableCell>
                            <TableCell>Assessment</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          <TableRow>
                            <TableCell>Ulcer Index</TableCell>
                            <TableCell align="right">{result.riskAnalysis.ulcerIndex.toFixed(2)}</TableCell>
                            <TableCell>
                              <Chip 
                                label={result.riskAnalysis.ulcerIndex < 5 ? 'Low' : 'High'} 
                                color={result.riskAnalysis.ulcerIndex < 5 ? 'success' : 'warning'}
                                size="small"
                              />
                            </TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell>Beta</TableCell>
                            <TableCell align="right">{result.metrics.beta.toFixed(2)}</TableCell>
                            <TableCell>
                              <Chip 
                                label={Math.abs(result.metrics.beta - 1) < 0.2 ? 'Market Neutral' : 'Market Sensitive'} 
                                color={Math.abs(result.metrics.beta - 1) < 0.2 ? 'success' : 'warning'}
                                size="small"
                              />
                            </TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell>Alpha</TableCell>
                            <TableCell align="right">{formatPercent(result.metrics.alpha)}</TableCell>
                            <TableCell>
                              <Chip 
                                label={result.metrics.alpha > 0 ? 'Positive' : 'Negative'} 
                                color={result.metrics.alpha > 0 ? 'success' : 'error'}
                                size="small"
                              />
                            </TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Grid>
                </Grid>
              </TabPanel>

              <TabPanel value={activeTab} index={3}>
                <Typography variant="h6" gutterBottom>Parameter Optimization</Typography>
                {optimizationResults.length > 0 ? (
                  <TableContainer component={Paper} variant="outlined">
                    <Table>
                      <TableHead>
                        <TableRow>
                          <TableCell>Rank</TableCell>
                          <TableCell>Parameters</TableCell>
                          <TableCell align="right">Sharpe Ratio</TableCell>
                          <TableCell align="right">Total Return</TableCell>
                          <TableCell align="right">Max Drawdown</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {optimizationResults.slice(0, 20).map((result, index) => (
                          <TableRow key={index} hover>
                            <TableCell>{index + 1}</TableCell>
                            <TableCell>
                              {Object.entries(result.parameters).map(([key, value]) => (
                                <Chip key={key} label={`${key}: ${value}`} size="small" sx={{ mr: 0.5, mb: 0.5 }} />
                              ))}
                            </TableCell>
                            <TableCell align="right">
                              <Typography color={getMetricColor('sharpeRatio', result.sharpeRatio)}>
                                {result.sharpeRatio.toFixed(2)}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">{formatPercent(result.totalReturn)}</TableCell>
                            <TableCell align="right">
                              <Typography color={getMetricColor('maxDrawdown', result.maxDrawdown)}>
                                {formatPercent(result.maxDrawdown)}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Alert severity="info">
                    Click "Optimize" to run parameter optimization analysis
                  </Alert>
                )}
              </TabPanel>

              <TabPanel value={activeTab} index={4}>
                <Typography variant="h6" gutterBottom>Monte Carlo Analysis</Typography>
                {result.monteCarlo && (
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <Typography variant="subtitle1" gutterBottom>
                        Return Distribution (1000 simulations)
                      </Typography>
                      <ResponsiveContainer width="100%" height={300}>
                        <BarChart 
                          data={result.monteCarlo.simulations
                            .reduce((acc, sim) => {
                              const bucket = Math.floor(sim.totalReturn * 10) / 10;
                              const existing = acc.find(item => item.bucket === bucket);
                              if (existing) {
                                existing.count++;
                              } else {
                                acc.push({ bucket, count: 1 });
                              }
                              return acc;
                            }, [])
                            .sort((a, b) => a.bucket - b.bucket)
                          }
                        >
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="bucket" tickFormatter={(value) => formatPercent(value)} />
                          <YAxis />
                          <RechartsTooltip formatter={(value) => [value, 'Count']} />
                          <Bar dataKey="count" fill="#2196f3" />
                        </BarChart>
                      </ResponsiveContainer>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <Typography variant="subtitle1" gutterBottom>
                        Percentile Analysis
                      </Typography>
                      <TableContainer component={Paper} variant="outlined">
                        <Table size="small">
                          <TableHead>
                            <TableRow>
                              <TableCell>Percentile</TableCell>
                              <TableCell align="right">Return</TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            <TableRow>
                              <TableCell>5th Percentile</TableCell>
                              <TableCell align="right" sx={{ color: 'error.main' }}>
                                {formatPercent(result.monteCarlo.percentiles.p5)}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell>25th Percentile</TableCell>
                              <TableCell align="right" sx={{ color: 'warning.main' }}>
                                {formatPercent(result.monteCarlo.percentiles.p25)}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell>50th Percentile (Median)</TableCell>
                              <TableCell align="right">
                                {formatPercent(result.monteCarlo.percentiles.p50)}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell>75th Percentile</TableCell>
                              <TableCell align="right" sx={{ color: 'success.main' }}>
                                {formatPercent(result.monteCarlo.percentiles.p75)}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell>95th Percentile</TableCell>
                              <TableCell align="right" sx={{ color: 'success.main' }}>
                                {formatPercent(result.monteCarlo.percentiles.p95)}
                              </TableCell>
                            </TableRow>
                          </TableBody>
                        </Table>
                      </TableContainer>
                    </Grid>
                  </Grid>
                )}
              </TabPanel>
            </Card>
          )}
        </Grid>
      </Grid>

      {/* Save Strategy Dialog */}
      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Save Backtest Result</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Result Name"
            fullWidth
            variant="outlined"
          />
          <TextField
            margin="dense"
            label="Description"
            fullWidth
            multiline
            rows={3}
            variant="outlined"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveDialogOpen(false)}>Cancel</Button>
          <Button onClick={() => setSaveDialogOpen(false)} variant="contained">Save</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}