import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Button,
  CircularProgress,
  Alert,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Tabs,
  Tab,
  LinearProgress,
  Tooltip,
  IconButton,
  Autocomplete,
  Slider,
  Switch,
  FormControlLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Avatar
} from '@mui/material';
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
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ScatterChart,
  Scatter,
  Cell,
  ReferenceLine
} from 'recharts';
import {
  Speed,
  Timeline,
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  Warning,
  CheckCircle,
  Info,
  Refresh as RefreshIcon,
  Download as DownloadIcon,
  Save as SaveIcon,
  Notifications,
  NotificationsActive,
  Psychology,
  Science,
  SettingsInputComponent,
  ShowChart,
  Whatshot,
  FlashOn,
  MonetizationOn,
  Security,
  AccountBalance,
  AccessTime,
  ExpandMore,
  ExpandLess
} from '@mui/icons-material';

// Generate realistic Greeks data for portfolio positions
const generatePortfolioPositions = (symbols) => {
  const positions = [];
  
  symbols.forEach((symbol, index) => {
    const spotPrice = 150 + (Math.random() - 0.5) * 100;
    const numOptions = Math.floor(Math.random() * 5) + 1;
    
    for (let i = 0; i < numOptions; i++) {
      const isCall = Math.random() > 0.5;
      const strike = spotPrice * (0.9 + Math.random() * 0.2);
      const quantity = (Math.floor(Math.random() * 20) + 1) * (Math.random() > 0.5 ? 1 : -1);
      const dte = Math.floor(Math.random() * 120) + 7;
      
      // Realistic Greeks calculations
      const moneyness = strike / spotPrice;
      const timeToExpiry = dte / 365;
      const volatility = 0.15 + Math.random() * 0.3;
      
      // Delta calculation (simplified)
      const delta = isCall ? 
        Math.max(0.01, Math.min(0.99, 0.5 + (spotPrice - strike) / (spotPrice * 0.3))) :
        Math.max(-0.99, Math.min(-0.01, -0.5 + (spotPrice - strike) / (spotPrice * 0.3)));
      
      // Gamma (highest for ATM options)
      const gamma = Math.max(0.001, 0.1 * Math.exp(-Math.pow((spotPrice - strike) / spotPrice, 2) / 0.02));
      
      // Theta (time decay)
      const theta = -Math.max(0.01, 0.05 * Math.sqrt(timeToExpiry) * volatility);
      
      // Vega (volatility sensitivity)
      const vega = Math.max(0.01, spotPrice * Math.sqrt(timeToExpiry) * 0.01);
      
      // Rho (interest rate sensitivity)
      const rho = isCall ? 
        Math.max(0.001, strike * timeToExpiry * 0.01 * delta) :
        Math.max(-0.1, -strike * timeToExpiry * 0.01 * Math.abs(delta));
      
      const optionPrice = Math.max(0.05, 
        Math.max(0, (isCall ? spotPrice - strike : strike - spotPrice)) + 
        volatility * Math.sqrt(timeToExpiry) * spotPrice * 0.4
      );
      
      positions.push({
        id: `${symbol}-${i}`,
        symbol,
        type: isCall ? 'CALL' : 'PUT',
        strike,
        expiry: new Date(Date.now() + dte * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        dte,
        quantity,
        spotPrice,
        optionPrice,
        delta: delta * quantity,
        gamma: gamma * quantity,
        theta: theta * quantity,
        vega: vega * quantity,
        rho: rho * quantity,
        notional: Math.abs(quantity) * optionPrice * 100,
        pnl: (Math.random() - 0.5) * 1000,
        impliedVol: volatility,
        moneyness: ((strike / spotPrice - 1) * 100)
      });
    }
  });
  
  return positions;
};

// Calculate portfolio-level Greeks
const calculatePortfolioGreeks = (positions) => {
  const totals = positions.reduce((acc, pos) => ({
    delta: acc.delta + pos.delta,
    gamma: acc.gamma + pos.gamma,
    theta: acc.theta + pos.theta,
    vega: acc.vega + pos.vega,
    rho: acc.rho + pos.rho,
    notional: acc.notional + pos.notional,
    pnl: acc.pnl + pos.pnl
  }), { delta: 0, gamma: 0, theta: 0, vega: 0, rho: 0, notional: 0, pnl: 0 });
  
  return totals;
};

// Greeks risk analysis
const analyzeGreeksRisk = (portfolioGreeks, positions) => {
  const risks = [];
  
  // Delta risk
  if (Math.abs(portfolioGreeks.delta) > 100) {
    risks.push({
      type: 'Delta Risk',
      level: Math.abs(portfolioGreeks.delta) > 500 ? 'High' : 'Medium',
      description: `Portfolio delta of ${portfolioGreeks.delta.toFixed(0)} creates significant directional exposure`,
      suggestion: 'Consider delta hedging with underlying shares or futures'
    });
  }
  
  // Gamma risk
  if (Math.abs(portfolioGreeks.gamma) > 10) {
    risks.push({
      type: 'Gamma Risk',
      level: Math.abs(portfolioGreeks.gamma) > 50 ? 'High' : 'Medium',
      description: `High gamma exposure of ${portfolioGreeks.gamma.toFixed(2)} creates delta instability`,
      suggestion: 'Monitor position sizing and consider gamma-neutral adjustments'
    });
  }
  
  // Theta decay
  if (portfolioGreeks.theta < -100) {
    risks.push({
      type: 'Time Decay',
      level: portfolioGreeks.theta < -500 ? 'High' : 'Medium',
      description: `Daily theta decay of $${Math.abs(portfolioGreeks.theta).toFixed(0)}`,
      suggestion: 'Monitor time decay especially into expiration'
    });
  }
  
  // Vega risk
  if (Math.abs(portfolioGreeks.vega) > 1000) {
    risks.push({
      type: 'Volatility Risk',
      level: Math.abs(portfolioGreeks.vega) > 5000 ? 'High' : 'Medium',
      description: `High vega exposure of ${portfolioGreeks.vega.toFixed(0)} to volatility changes`,
      suggestion: 'Consider volatility hedging strategies'
    });
  }
  
  return risks;
};

// Generate Greeks scenarios
const generateGreeksScenarios = (portfolioGreeks, currentPrice) => {
  const scenarios = [];
  const priceChanges = [-10, -5, -2, -1, 0, 1, 2, 5, 10];
  const volChanges = [-5, -2, -1, 0, 1, 2, 5];
  
  priceChanges.forEach(priceChange => {
    const newPrice = currentPrice * (1 + priceChange / 100);
    const deltaPnL = portfolioGreeks.delta * (newPrice - currentPrice);
    const gammaPnL = 0.5 * portfolioGreeks.gamma * Math.pow(newPrice - currentPrice, 2);
    const totalPnL = deltaPnL + gammaPnL;
    
    scenarios.push({
      priceChange: `${priceChange > 0 ? '+' : ''}${priceChange}%`,
      newPrice: newPrice.toFixed(2),
      deltaPnL: deltaPnL.toFixed(0),
      gammaPnL: gammaPnL.toFixed(0),
      totalPnL: totalPnL.toFixed(0),
      priceChangeNum: priceChange
    });
  });
  
  return scenarios;
};

const GreeksMonitor = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [selectedPortfolio, setSelectedPortfolio] = useState('main');
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(30); // seconds
  
  // Data states
  const [positions, setPositions] = useState([]);
  const [portfolioGreeks, setPortfolioGreeks] = useState(null);
  const [greeksHistory, setGreeksHistory] = useState([]);
  const [riskAnalysis, setRiskAnalysis] = useState([]);
  const [scenarios, setScenarios] = useState([]);
  const [alerts, setAlerts] = useState([]);
  
  // Controls
  const [deltaThreshold, setDeltaThreshold] = useState(500);
  const [gammaThreshold, setGammaThreshold] = useState(50);
  const [thetaThreshold, setThetaThreshold] = useState(-200);
  const [vegaThreshold, setVegaThreshold] = useState(2000);
  
  const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ'];
  const portfolios = ['main', 'hedge', 'speculative', 'income'];
  
  useEffect(() => {
    loadGreeksData();
    
    if (autoRefresh) {
      const interval = setInterval(loadGreeksData, refreshInterval * 1000);
      return () => clearInterval(interval);
    }
  }, [selectedPortfolio, autoRefresh, refreshInterval]);
  
  const loadGreeksData = () => {
    setLoading(true);
    
    try {
      const positionsData = generatePortfolioPositions(symbols);
      const portfolioTotals = calculatePortfolioGreeks(positionsData);
      const risks = analyzeGreeksRisk(portfolioTotals, positionsData);
      const scenarioData = generateGreeksScenarios(portfolioTotals, 150);
      
      // Generate historical Greeks data
      const history = [];
      for (let i = 30; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        history.push({
          date: date.toISOString().split('T')[0],
          delta: portfolioTotals.delta + (Math.random() - 0.5) * 100,
          gamma: portfolioTotals.gamma + (Math.random() - 0.5) * 10,
          theta: portfolioTotals.theta + (Math.random() - 0.5) * 50,
          vega: portfolioTotals.vega + (Math.random() - 0.5) * 500,
          pnl: portfolioTotals.pnl + (Math.random() - 0.5) * 2000
        });
      }
      
      setPositions(positionsData);
      setPortfolioGreeks(portfolioTotals);
      setGreeksHistory(history);
      setRiskAnalysis(risks);
      setScenarios(scenarioData);
      
    } catch (err) {
      setError('Failed to load Greeks data');
    } finally {
      setLoading(false);
    }
  };
  
  const getGreekColor = (value, type) => {
    switch (type) {
      case 'delta':
        return Math.abs(value) > deltaThreshold ? 'error.main' : 'success.main';
      case 'gamma':
        return Math.abs(value) > gammaThreshold ? 'error.main' : 'warning.main';
      case 'theta':
        return value < thetaThreshold ? 'error.main' : 'warning.main';
      case 'vega':
        return Math.abs(value) > vegaThreshold ? 'error.main' : 'info.main';
      default:
        return 'text.primary';
    }
  };
  
  const getRiskLevelColor = (level) => {
    switch (level) {
      case 'High': return 'error';
      case 'Medium': return 'warning';
      case 'Low': return 'success';
      default: return 'default';
    }
  };
  
  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          Greeks Portfolio Monitor
        </div>
        <div  variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Real-time portfolio Greeks monitoring, risk analysis, and scenario planning for options portfolios
        </div>
        <div  display="flex" gap={1} flexWrap="wrap">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Live Greeks" color="primary" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Risk Alerts" color="error" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Scenario Analysis" color="warning" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Portfolio Hedging" color="success" size="small" variant="outlined" />
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </div>
      )}

      {/* Controls */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Portfolio</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={selectedPortfolio}
                  label="Portfolio"
                  onChange={(e) => setSelectedPortfolio(e.target.value)}
                >
                  {portfolios.map(portfolio => (
                    <option  key={portfolio} value={portfolio}>
                      {portfolio.charAt(0).toUpperCase() + portfolio.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle" 
                    checked={autoRefresh} 
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                  />
                }
                label="Auto Refresh"
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Interval (sec)"
                type="number"
                value={refreshInterval}
                onChange={(e) => setRefreshInterval(parseInt(e.target.value))}
                size="small"
                fullWidth
                disabled={!autoRefresh}
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                startIcon={loading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} /> : <↻  />}
                onClick={loadGreeksData}
                disabled={loading}
                fullWidth
              >
                Refresh
              </button>
            </div>
            <div className="grid" item xs={12} sm={4}>
              {portfolioGreeks && (
                <div  display="flex" gap={2}>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Total P&L</div>
                    <div  
                      variant="h6" 
                      fontWeight="bold"
                      color={portfolioGreeks.pnl >= 0 ? 'success.main' : 'error.main'}
                    >
                      ${portfolioGreeks.pnl.toFixed(0)}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Positions</div>
                    <div  variant="h6" fontWeight="bold">
                      {positions.length}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Notional</div>
                    <div  variant="h6" fontWeight="bold">
                      ${(portfolioGreeks.notional / 1000).toFixed(0)}K
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid" container spacing={3}>
        {/* Main Greeks Dashboard */}
        <div className="grid" item xs={12} lg={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header 
              title="Portfolio Greeks Dashboard"
              subheader={`Last updated: ${new Date().toLocaleTimeString()}`}
              action={
                <div  display="flex" gap={1}>
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle" 
                        checked={alertsEnabled} 
                        onChange={(e) => setAlertsEnabled(e.target.checked)}
                      />
                    }
                    label="Alerts"
                  />
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" startIcon={<SaveIcon />} size="small">
                    Save
                  </button>
                </div>
              }
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="border-b border-gray-200" value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Greeks Summary" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Position Details" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Risk Analysis" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Scenarios" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="History" />
              </div>
              
              {activeTab === 0 && portfolioGreeks && (
                <div className="grid" container spacing={3}>
                  <div className="grid" item xs={12} md={6}>
                    <div  variant="h6" gutterBottom>Portfolio Greeks</div>
                    <div className="grid" container spacing={2}>
                      <div className="grid" item xs={6}>
                        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                          <div  
                            variant="h4" 
                            fontWeight="bold"
                            color={getGreekColor(portfolioGreeks.delta, 'delta')}
                          >
                            {portfolioGreeks.delta.toFixed(0)}
                          </div>
                          <div  variant="caption">Delta</div>
                          <div  variant="body2" color="text.secondary">
                            $1 move = ${portfolioGreeks.delta.toFixed(0)} P&L
                          </div>
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                          <div  
                            variant="h4" 
                            fontWeight="bold"
                            color={getGreekColor(portfolioGreeks.gamma, 'gamma')}
                          >
                            {portfolioGreeks.gamma.toFixed(1)}
                          </div>
                          <div  variant="caption">Gamma</div>
                          <div  variant="body2" color="text.secondary">
                            Delta change rate
                          </div>
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                          <div  
                            variant="h4" 
                            fontWeight="bold"
                            color={getGreekColor(portfolioGreeks.theta, 'theta')}
                          >
                            {portfolioGreeks.theta.toFixed(0)}
                          </div>
                          <div  variant="caption">Theta</div>
                          <div  variant="body2" color="text.secondary">
                            Daily time decay
                          </div>
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                          <div  
                            variant="h4" 
                            fontWeight="bold"
                            color={getGreekColor(portfolioGreeks.vega, 'vega')}
                          >
                            {portfolioGreeks.vega.toFixed(0)}
                          </div>
                          <div  variant="caption">Vega</div>
                          <div  variant="body2" color="text.secondary">
                            1% vol change impact
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={12} md={6}>
                    <div  variant="h6" gutterBottom>Greeks Distribution</div>
                    <ResponsiveContainer width="100%" height={250}>
                      <RadarChart data={[
                        { 
                          greek: 'Delta', 
                          value: Math.abs(portfolioGreeks.delta) / 1000,
                          fullMark: 1
                        },
                        { 
                          greek: 'Gamma', 
                          value: Math.abs(portfolioGreeks.gamma) / 100,
                          fullMark: 1
                        },
                        { 
                          greek: 'Theta', 
                          value: Math.abs(portfolioGreeks.theta) / 500,
                          fullMark: 1
                        },
                        { 
                          greek: 'Vega', 
                          value: Math.abs(portfolioGreeks.vega) / 5000,
                          fullMark: 1
                        },
                        { 
                          greek: 'Rho', 
                          value: Math.abs(portfolioGreeks.rho) / 100,
                          fullMark: 1
                        }
                      ]}>
                        <PolarGrid />
                        <PolarAngleAxis dataKey="greek" />
                        <PolarRadiusAxis domain={[0, 1]} tick={false} />
                        <Radar 
                          name="Greeks" 
                          dataKey="value" 
                          stroke="#8884d8" 
                          fill="#8884d8" 
                          fillOpacity={0.3}
                        />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
              
              {activeTab === 1 && (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined" sx={{ maxHeight: 500 }}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Type</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Qty</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Strike</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">DTE</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Delta</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Gamma</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Theta</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Vega</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">P&L</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {positions.map((position) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={position.id} hover>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  variant="body2" fontWeight="bold">
                              {position.symbol}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={position.type} 
                              color={position.type === 'CALL' ? 'success' : 'error'}
                              size="small"
                              variant="outlined"
                            />
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  
                              variant="body2"
                              color={position.quantity > 0 ? 'success.main' : 'error.main'}
                            >
                              {position.quantity > 0 ? '+' : ''}{position.quantity}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${position.strike.toFixed(2)}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{position.dte}d</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  sx={{ color: getGreekColor(position.delta, 'delta') }}>
                              {position.delta.toFixed(1)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  sx={{ color: getGreekColor(position.gamma, 'gamma') }}>
                              {position.gamma.toFixed(3)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  sx={{ color: getGreekColor(position.theta, 'theta') }}>
                              {position.theta.toFixed(2)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  sx={{ color: getGreekColor(position.vega, 'vega') }}>
                              {position.vega.toFixed(1)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  
                              variant="body2"
                              color={position.pnl >= 0 ? 'success.main' : 'error.main'}
                              fontWeight="bold"
                            >
                              ${position.pnl.toFixed(0)}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              
              {activeTab === 2 && (
                <div>
                  <div  variant="h6" gutterBottom>Risk Analysis</div>
                  <div className="grid" container spacing={2}>
                    {riskAnalysis.map((risk, index) => (
                      <div className="grid" item xs={12} md={6} key={index}>
                        <div className="bg-white shadow-md rounded-lg" variant="outlined">
                          <div className="bg-white shadow-md rounded-lg"Content>
                            <div  display="flex" alignItems="center" gap={1} mb={1}>
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                label={risk.level} 
                                color={getRiskLevelColor(risk.level)}
                                size="small"
                              />
                              <div  variant="subtitle1" fontWeight="bold">
                                {risk.type}
                              </div>
                            </div>
                            <div  variant="body2" color="text.secondary" paragraph>
                              {risk.description}
                            </div>
                            <div  variant="body2" color="primary.main">
                              💡 {risk.suggestion}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {activeTab === 3 && (
                <div>
                  <div  variant="h6" gutterBottom>Scenario Analysis</div>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Price Change</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">New Price</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Delta P&L</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Gamma P&L</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Total P&L</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Impact</td>
                        </tr>
                      </thead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                        {scenarios.map((scenario, index) => (
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow 
                            key={index} 
                            hover
                            sx={{ 
                              bgcolor: scenario.priceChangeNum === 0 ? 'action.hover' : 'inherit'
                            }}
                          >
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                              <div  
                                variant="body2" 
                                fontWeight={scenario.priceChangeNum === 0 ? 'bold' : 'normal'}
                              >
                                {scenario.priceChange}
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${scenario.newPrice}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div  
                                variant="body2"
                                color={parseFloat(scenario.deltaPnL) >= 0 ? 'success.main' : 'error.main'}
                              >
                                ${scenario.deltaPnL}
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div  
                                variant="body2"
                                color={parseFloat(scenario.gammaPnL) >= 0 ? 'success.main' : 'error.main'}
                              >
                                ${scenario.gammaPnL}
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div  
                                variant="body2"
                                color={parseFloat(scenario.totalPnL) >= 0 ? 'success.main' : 'error.main'}
                                fontWeight="bold"
                              >
                                ${scenario.totalPnL}
                              </div>
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                              <div className="w-full bg-gray-200 rounded-full h-2" 
                                variant="determinate" 
                                value={Math.min(100, Math.abs(parseFloat(scenario.totalPnL)) / 100)} 
                                color={parseFloat(scenario.totalPnL) >= 0 ? 'success' : 'error'}
                                sx={{ width: 50 }}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              
              {activeTab === 4 && (
                <div>
                  <div  variant="h6" gutterBottom>Greeks History (30 Days)</div>
                  <ResponsiveContainer width="100%" height={400}>
                    <LineChart data={greeksHistory}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip />
                      <Line type="monotone" dataKey="delta" stroke="#8884d8" name="Delta" />
                      <Line type="monotone" dataKey="gamma" stroke="#82ca9d" name="Gamma" />
                      <Line type="monotone" dataKey="theta" stroke="#ffc658" name="Theta" />
                      <Line type="monotone" dataKey="vega" stroke="#ff7300" name="Vega" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="grid" item xs={12} lg={4}>
          {/* Risk Thresholds */}
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
            <div className="bg-white shadow-md rounded-lg"Header title="Risk Thresholds" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ mb: 2 }}>
                <div  variant="subtitle2" gutterBottom>
                  Delta Threshold: {deltaThreshold}
                </div>
                <Slider
                  value={deltaThreshold}
                  onChange={(_, value) => setDeltaThreshold(value)}
                  min={100}
                  max={1000}
                  step={50}
                  valueLabelDisplay="auto"
                />
              </div>
              <div  sx={{ mb: 2 }}>
                <div  variant="subtitle2" gutterBottom>
                  Gamma Threshold: {gammaThreshold}
                </div>
                <Slider
                  value={gammaThreshold}
                  onChange={(_, value) => setGammaThreshold(value)}
                  min={10}
                  max={100}
                  step={5}
                  valueLabelDisplay="auto"
                />
              </div>
              <div  sx={{ mb: 2 }}>
                <div  variant="subtitle2" gutterBottom>
                  Theta Threshold: {thetaThreshold}
                </div>
                <Slider
                  value={thetaThreshold}
                  onChange={(_, value) => setThetaThreshold(value)}
                  min={-500}
                  max={-50}
                  step={25}
                  valueLabelDisplay="auto"
                />
              </div>
              <div>
                <div  variant="subtitle2" gutterBottom>
                  Vega Threshold: {vegaThreshold}
                </div>
                <Slider
                  value={vegaThreshold}
                  onChange={(_, value) => setVegaThreshold(value)}
                  min={500}
                  max={5000}
                  step={250}
                  valueLabelDisplay="auto"
                />
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Quick Actions" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="grid" container spacing={1}>
                <div className="grid" item xs={6}>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" fullWidth size="small" startIcon={<Security />}>
                    Delta Hedge
                  </button>
                </div>
                <div className="grid" item xs={6}>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" fullWidth size="small" startIcon={<Speed />}>
                    Gamma Adjust
                  </button>
                </div>
                <div className="grid" item xs={6}>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" fullWidth size="small" startIcon={<AccessTime />}>
                    Roll Positions
                  </button>
                </div>
                <div className="grid" item xs={6}>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" fullWidth size="small" startIcon={<ShowChart />}>
                    Vol Hedge
                  </button>
                </div>
              </div>
              <hr className="border-gray-200" sx={{ my: 2 }} />
              <div  variant="subtitle2" gutterBottom>
                Hedging Suggestions
              </div>
              <div  variant="body2" color="text.secondary">
                Based on current Greeks exposure, consider:
                • Delta hedging with {Math.abs(portfolioGreeks?.delta || 0).toFixed(0)} shares
                • Monitor gamma risk before major moves
                • Time decay acceleration near expiration
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GreeksMonitor;