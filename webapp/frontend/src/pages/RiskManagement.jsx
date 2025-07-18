import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  LinearProgress,
  Divider,
  Badge,
  Tooltip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Switch,
  FormControlLabel,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  ListItemSecondaryAction,
  Autocomplete,
  SpeedDial,
  SpeedDialAction,
  SpeedDialIcon
} from '@mui/material';
import {
  Security,
  Warning,
  TrendingUp,
  TrendingDown,
  Assessment,
  Timeline,
  Shield,
  Error as ErrorIcon,
  CheckCircle,
  ExpandMore,
  Refresh,
  Download,
  Settings,
  Notifications,
  Speed,
  NotificationsActive,
  Psychology,
  MonetizationOn,
  AccountBalance,
  Analytics,
  Whatshot,
  FlashOn,
  Science,
  HealthAndSafety,
  Tune,
  Save as SaveIcon,
  PlayArrow,
  Stop,
  Pause,
  AccessTime,
  TrendingFlat,
  ShowChart,
  BarChart as BarChartIcon,
  PieChart as PieChartIcon
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  ScatterChart,
  Scatter,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ReferenceLine
} from 'recharts';
import { getApiConfig } from '../services/api';

const { apiUrl: API_BASE } = getApiConfig();

// Advanced risk calculation functions
const calculateVaR = (returns, confidence = 0.95) => {
  if (!returns || returns.length === 0) return 0;
  const sortedReturns = [...returns].sort((a, b) => a - b);
  const index = Math.floor((1 - confidence) * sortedReturns.length);
  return Math.abs(sortedReturns[index] || 0);
};

const calculateCVaR = (returns, confidence = 0.95) => {
  if (!returns || returns.length === 0) return 0;
  const sortedReturns = [...returns].sort((a, b) => a - b);
  const cutoff = Math.floor((1 - confidence) * sortedReturns.length);
  const tailReturns = sortedReturns.slice(0, cutoff);
  return Math.abs(tailReturns.reduce((sum, ret) => sum + ret, 0) / tailReturns.length);
};

const calculateMaxDrawdown = (values) => {
  if (!values || values.length === 0) return 0;
  let peak = values[0];
  let maxDrawdown = 0;
  
  for (let i = 1; i < values.length; i++) {
    if (values[i] > peak) {
      peak = values[i];
    } else {
      const drawdown = (peak - values[i]) / peak;
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
    }
  }
  return maxDrawdown;
};

const calculateSharpeRatio = (returns, riskFreeRate = 0.02) => {
  if (!returns || returns.length === 0) return 0;
  const mean = returns.reduce((sum, ret) => sum + ret, 0) / returns.length;
  const variance = returns.reduce((sum, ret) => sum + Math.pow(ret - mean, 2), 0) / returns.length;
  const volatility = Math.sqrt(variance);
  return volatility === 0 ? 0 : (mean - riskFreeRate) / volatility;
};

const calculateBeta = (assetReturns, marketReturns) => {
  if (!assetReturns || !marketReturns || assetReturns.length !== marketReturns.length) return 1;
  
  const assetMean = assetReturns.reduce((sum, ret) => sum + ret, 0) / assetReturns.length;
  const marketMean = marketReturns.reduce((sum, ret) => sum + ret, 0) / marketReturns.length;
  
  let numerator = 0;
  let denominator = 0;
  
  for (let i = 0; i < assetReturns.length; i++) {
    numerator += (assetReturns[i] - assetMean) * (marketReturns[i] - marketMean);
    denominator += Math.pow(marketReturns[i] - marketMean, 2);
  }
  
  return denominator === 0 ? 1 : numerator / denominator;
};

// Generate comprehensive risk data
const generateAdvancedRiskData = (symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ', 'IWM']) => {
  const positions = [];
  
  // Generate realistic portfolio positions with advanced metrics
  symbols.forEach((symbol, index) => {
    const weight = Math.random() * 0.15 + 0.05; // 5-20% allocation
    const price = 150 + (Math.random() - 0.5) * 100;
    const quantity = Math.floor(Math.random() * 1000) + 100;
    const value = price * quantity;
    
    // Generate historical returns for advanced calculations
    const returns = Array.from({ length: 252 }, () => (Math.random() - 0.5) * 0.1); // Daily returns
    const marketReturns = Array.from({ length: 252 }, () => (Math.random() - 0.5) * 0.08);
    
    const volatility = Math.sqrt(returns.reduce((sum, ret) => sum + ret * ret, 0) / returns.length) * Math.sqrt(252);
    const beta = calculateBeta(returns, marketReturns);
    const sharpe = calculateSharpeRatio(returns);
    const var95 = calculateVaR(returns.map(r => r * value)) * Math.sqrt(252);
    const cvar95 = calculateCVaR(returns.map(r => r * value)) * Math.sqrt(252);
    
    positions.push({
      symbol,
      weight,
      price,
      quantity,
      value,
      volatility,
      beta,
      sharpe,
      var95,
      cvar95,
      returns,
      correlation: 0.3 + Math.random() * 0.6,
      concentration: weight,
      sector: ['Technology', 'Healthcare', 'Finance', 'Energy'][Math.floor(Math.random() * 4)],
      riskRating: Math.random() > 0.7 ? 'High' : Math.random() > 0.3 ? 'Medium' : 'Low'
    });
  });
  
  const totalValue = positions.reduce((sum, pos) => sum + pos.value, 0);
  const portfolioReturns = Array.from({ length: 252 }, (_, i) => 
    positions.reduce((sum, pos) => sum + pos.returns[i] * pos.weight, 0)
  );
  
  const portfolioMetrics = {
    totalValue,
    var95: calculateVaR(portfolioReturns.map(r => r * totalValue)) * Math.sqrt(252),
    cvar95: calculateCVaR(portfolioReturns.map(r => r * totalValue)) * Math.sqrt(252),
    var99: calculateVaR(portfolioReturns.map(r => r * totalValue), 0.99) * Math.sqrt(252),
    sharpeRatio: calculateSharpeRatio(portfolioReturns),
    volatility: Math.sqrt(portfolioReturns.reduce((sum, ret) => sum + ret * ret, 0) / portfolioReturns.length) * Math.sqrt(252),
    beta: positions.reduce((sum, pos) => sum + pos.beta * pos.weight, 0),
    maxDrawdown: calculateMaxDrawdown(portfolioReturns.map((_, i) => 
      portfolioReturns.slice(0, i + 1).reduce((sum, ret) => sum * (1 + ret), totalValue)
    )),
    correlation: positions.reduce((sum, pos) => sum + pos.correlation * pos.weight, 0),
    concentrationRisk: Math.max(...positions.map(pos => pos.weight)),
    diversificationRatio: 1 / Math.sqrt(positions.reduce((sum, pos) => sum + pos.weight * pos.weight, 0)),
    trackingError: Math.sqrt(portfolioReturns.reduce((sum, ret) => sum + Math.pow(ret - 0.001, 2), 0) / portfolioReturns.length) * Math.sqrt(252),
    informationRatio: calculateSharpeRatio(portfolioReturns.map(ret => ret - 0.001)),
    calmarRatio: portfolioReturns.reduce((sum, ret) => sum + ret, 0) / portfolioReturns.length / calculateMaxDrawdown(portfolioReturns)
  };
  
  // Risk factor exposures
  const riskFactors = [
    { name: 'Market Risk', exposure: 0.85, contribution: 0.45 },
    { name: 'Size Factor', exposure: 0.12, contribution: 0.08 },
    { name: 'Value Factor', exposure: -0.05, contribution: 0.03 },
    { name: 'Momentum Factor', exposure: 0.18, contribution: 0.12 },
    { name: 'Quality Factor', exposure: 0.22, contribution: 0.15 },
    { name: 'Volatility Factor', exposure: -0.08, contribution: 0.05 },
    { name: 'Sector Concentration', exposure: 0.35, contribution: 0.25 }
  ];
  
  // Stress test scenarios
  const stressTests = [
    { 
      name: '2008 Financial Crisis', 
      marketDrop: -37.0, 
      portfolioLoss: -312500, 
      probability: 0.5,
      timeHorizon: '1 Year',
      worstCase: -450000,
      expectedShortfall: -385000
    },
    { 
      name: 'COVID-19 Crash (Mar 2020)', 
      marketDrop: -34.0, 
      portfolioLoss: -287500, 
      probability: 2.0,
      timeHorizon: '6 Months',
      worstCase: -350000,
      expectedShortfall: -320000
    },
    { 
      name: 'Tech Bubble Burst', 
      marketDrop: -45.0, 
      portfolioLoss: -425000, 
      probability: 1.0,
      timeHorizon: '2 Years',
      worstCase: -550000,
      expectedShortfall: -485000
    },
    { 
      name: 'Flash Crash', 
      marketDrop: -9.0, 
      portfolioLoss: -95000, 
      probability: 5.0,
      timeHorizon: '1 Day',
      worstCase: -125000,
      expectedShortfall: -110000
    },
    { 
      name: 'Interest Rate Shock', 
      marketDrop: -15.0, 
      portfolioLoss: -165000, 
      probability: 10.0,
      timeHorizon: '3 Months',
      worstCase: -210000,
      expectedShortfall: -185000
    }
  ];
  
  // Risk alerts with different severity levels
  const riskAlerts = [
    {
      id: 1,
      symbol: 'TSLA',
      metric: 'Individual VaR',
      value: 45000,
      threshold: 35000,
      severity: 'high',
      timestamp: new Date(Date.now() - 30 * 60 * 1000),
      description: 'Position VaR exceeds individual limit',
      recommendation: 'Consider reducing position size or hedging'
    },
    {
      id: 2,
      symbol: 'PORTFOLIO',
      metric: 'Concentration Risk',
      value: 0.35,
      threshold: 0.30,
      severity: 'medium',
      timestamp: new Date(Date.now() - 45 * 60 * 1000),
      description: 'Portfolio concentration above optimal level',
      recommendation: 'Rebalance positions to improve diversification'
    },
    {
      id: 3,
      symbol: 'NVDA',
      metric: 'Correlation Increase',
      value: 0.85,
      threshold: 0.75,
      severity: 'medium',
      timestamp: new Date(Date.now() - 60 * 60 * 1000),
      description: 'Position correlation with market increased significantly',
      recommendation: 'Monitor for potential systematic risk'
    },
    {
      id: 4,
      symbol: 'PORTFOLIO',
      metric: 'Volatility Spike',
      value: 0.28,
      threshold: 0.25,
      severity: 'low',
      timestamp: new Date(Date.now() - 90 * 60 * 1000),
      description: 'Portfolio volatility above target range',
      recommendation: 'Review position sizes and consider volatility hedging'
    }
  ];
  
  // Historical VaR and risk metrics
  const historicalMetrics = Array.from({ length: 30 }, (_, i) => {
    const date = new Date();
    date.setDate(date.getDate() - (29 - i));
    return {
      date: date.toISOString().split('T')[0],
      var95: portfolioMetrics.var95 + (Math.random() - 0.5) * 20000,
      var99: portfolioMetrics.var99 + (Math.random() - 0.5) * 35000,
      cvar95: portfolioMetrics.cvar95 + (Math.random() - 0.5) * 25000,
      sharpe: portfolioMetrics.sharpeRatio + (Math.random() - 0.5) * 0.3,
      volatility: portfolioMetrics.volatility + (Math.random() - 0.5) * 0.05,
      beta: portfolioMetrics.beta + (Math.random() - 0.5) * 0.2,
      maxDD: portfolioMetrics.maxDrawdown + (Math.random() - 0.5) * 0.05
    };
  });
  
  return {
    portfolioMetrics,
    positions,
    riskFactors,
    stressTests,
    riskAlerts,
    historicalMetrics,
    lastUpdated: new Date()
  };
};

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`risk-tabpanel-${index}`}
      aria-labelledby={`risk-tab-${index}`}
      {...other}
    >
      {value === index && (
        <div  sx={{ py: 3 }}>
          {children}
        </div>
      )}
    </div>
  );
}

const RiskManagement = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [riskData, setRiskData] = useState(null);
  const [symbols, setSymbols] = useState(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ', 'IWM']);
  const [realTimeEnabled, setRealTimeEnabled] = useState(true);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedTimeHorizon, setSelectedTimeHorizon] = useState('1D');
  const [confidenceLevel, setConfidenceLevel] = useState(95);
  const [alertThresholds, setAlertThresholds] = useState({
    portfolioVaR: 100000,
    concentrationLimit: 0.30,
    volatilityLimit: 0.25,
    betaLimit: 1.5,
    correlationLimit: 0.80
  });
  
  const [newAlert, setNewAlert] = useState({
    symbol: '',
    metric: 'var',
    threshold: 50000,
    condition: 'above',
    enabled: true
  });

  // Load symbols from symbol service
  useEffect(() => {
    const loadSymbols = async () => {
      try {
        const { symbolService } = await import('../services/symbolService');
        const dynamicSymbols = await symbolService.getSymbols('popular', { limit: 20 });
        if (dynamicSymbols.length > 0) {
          setSymbols(dynamicSymbols);
        }
      } catch (error) {
        console.error('Failed to load symbols for risk management:', error);
        // Keep default symbols on error
      }
    };
    loadSymbols();
  }, []);

  useEffect(() => {
    loadRiskData();
    
    if (realTimeEnabled) {
      const interval = setInterval(loadRiskData, 30000); // Update every 30 seconds
      return () => clearInterval(interval);
    }
  }, [realTimeEnabled, selectedTimeHorizon, confidenceLevel, symbols]);

  const loadRiskData = useCallback(async () => {
    setLoading(true);
    try {
      // Simulate API call - replace with real risk service
      await new Promise(resolve => setTimeout(resolve, 1000));
      const data = generateAdvancedRiskData(symbols);
      setRiskData(data);
    } catch (error) {
      console.error('Error loading risk data:', error);
    } finally {
      setLoading(false);
    }
  }, [symbols]);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const getRiskColor = (value, thresholds) => {
    if (value <= thresholds.low) return 'success';
    if (value <= thresholds.medium) return 'warning';
    return 'error';
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'high': return <ErrorIcon color="error" />;
      case 'medium': return <Warning color="warning" />;
      case 'low': return <CheckCircle color="success" />;
      default: return <CheckCircle color="success" />;
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const formatPercent = (value) => {
    return `${(value * 100).toFixed(2)}%`;
  };

  const handleCreateAlert = () => {
    console.log('Creating risk alert:', newAlert);
    setAlertDialogOpen(false);
    setNewAlert({
      symbol: '',
      metric: 'var',
      threshold: 50000,
      condition: 'above',
      enabled: true
    });
  };

  if (loading && !riskData) {
    return (
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 3 }}>
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 3 }}>
      {/* Header */}
      <div  sx={{ mb: 3 }}>
        <div  variant="h4" gutterBottom sx={{ fontWeight: 700, display: 'flex', alignItems: 'center' }}>
          <Security sx={{ mr: 2, color: 'primary.main' }} />
          Advanced Risk Management
        </div>
        <div  variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Institutional-grade portfolio risk monitoring with real-time analytics, stress testing, and predictive alerts
        </div>
        <div  display="flex" gap={1} flexWrap="wrap">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Real-time VaR" color="primary" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Stress Testing" color="error" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Factor Attribution" color="info" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Predictive Alerts" color="warning" size="small" variant="outlined" />
        </div>
      </div>

      {/* Control Panel */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Time Horizon</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={selectedTimeHorizon}
                  label="Time Horizon"
                  onChange={(e) => setSelectedTimeHorizon(e.target.value)}
                >
                  <option  value="1D">1 Day</option>
                  <option  value="1W">1 Week</option>
                  <option  value="1M">1 Month</option>
                  <option  value="3M">3 Months</option>
                  <option  value="1Y">1 Year</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Confidence Level</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={confidenceLevel}
                  label="Confidence Level"
                  onChange={(e) => setConfidenceLevel(e.target.value)}
                >
                  <option  value={90}>90%</option>
                  <option  value={95}>95%</option>
                  <option  value={99}>99%</option>
                  <option  value={99.9}>99.9%</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle"
                    checked={realTimeEnabled}
                    onChange={(e) => setRealTimeEnabled(e.target.checked)}
                  />
                }
                label="Real-time"
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={loading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} /> : <Refresh />}
                onClick={loadRiskData}
                disabled={loading}
                fullWidth
              >
                Refresh
              </button>
            </div>
            <div className="grid" item xs={12} sm={4}>
              {riskData && (
                <div  display="flex" gap={2}>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Portfolio Value</div>
                    <div  variant="h6" fontWeight="bold">
                      {formatCurrency(riskData.portfolioMetrics.totalValue)}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Active Alerts</div>
                    <div  variant="h6" fontWeight="bold" color="error.main">
                      {riskData.riskAlerts.length}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Last Update</div>
                    <div  variant="h6" fontWeight="bold">
                      {riskData.lastUpdated.toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Key Risk Metrics Cards */}
      <div className="grid" container spacing={3} sx={{ mb: 3 }}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div  color="text.secondary" gutterBottom>VaR ({confidenceLevel}%)</div>
                  <div  variant="h5" sx={{ fontWeight: 700, color: 'error.main' }}>
                    {formatCurrency(riskData?.portfolioMetrics.var95)}
                  </div>
                  <div  variant="caption" color="text.secondary">
                    {formatPercent(riskData?.portfolioMetrics.var95 / riskData?.portfolioMetrics.totalValue)} of portfolio
                  </div>
                </div>
                <Shield sx={{ fontSize: 48, color: 'error.main', opacity: 0.7 }} />
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={(riskData?.portfolioMetrics.var95 / riskData?.portfolioMetrics.totalValue) * 100} 
                sx={{ mt: 2 }}
                color="error"
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div  color="text.secondary" gutterBottom>Expected Shortfall</div>
                  <div  variant="h5" sx={{ fontWeight: 700, color: 'warning.main' }}>
                    {formatCurrency(riskData?.portfolioMetrics.cvar95)}
                  </div>
                  <div  variant="caption" color="text.secondary">
                    Tail risk beyond VaR
                  </div>
                </div>
                <TrendingDown sx={{ fontSize: 48, color: 'warning.main', opacity: 0.7 }} />
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label="CVaR Analysis" 
                color="warning" 
                size="small" 
                sx={{ mt: 2 }}
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div  color="text.secondary" gutterBottom>Sharpe Ratio</div>
                  <div  variant="h5" sx={{ 
                    fontWeight: 700, 
                    color: riskData?.portfolioMetrics.sharpeRatio > 1 ? 'success.main' : 'warning.main' 
                  }}>
                    {riskData?.portfolioMetrics.sharpeRatio.toFixed(2)}
                  </div>
                  <div  variant="caption" color="text.secondary">
                    Risk-adjusted return
                  </div>
                </div>
                <Assessment sx={{ 
                  fontSize: 48, 
                  color: riskData?.portfolioMetrics.sharpeRatio > 1 ? 'success.main' : 'warning.main',
                  opacity: 0.7 
                }} />
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={riskData?.portfolioMetrics.sharpeRatio > 1.5 ? 'Excellent' : 
                      riskData?.portfolioMetrics.sharpeRatio > 1 ? 'Good' : 
                      riskData?.portfolioMetrics.sharpeRatio > 0.5 ? 'Fair' : 'Poor'} 
                color={riskData?.portfolioMetrics.sharpeRatio > 1 ? 'success' : 'warning'} 
                size="small" 
                sx={{ mt: 2 }}
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div  color="text.secondary" gutterBottom>Max Drawdown</div>
                  <div  variant="h5" sx={{ fontWeight: 700, color: 'error.main' }}>
                    {formatPercent(riskData?.portfolioMetrics.maxDrawdown)}
                  </div>
                  <div  variant="caption" color="text.secondary">
                    Peak-to-trough decline
                  </div>
                </div>
                <TrendingDown sx={{ fontSize: 48, color: 'error.main', opacity: 0.7 }} />
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={riskData?.portfolioMetrics.maxDrawdown * 100} 
                sx={{ mt: 2 }}
                color={getRiskColor(riskData?.portfolioMetrics.maxDrawdown * 100, { low: 10, medium: 20 })}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Main Risk Analysis Tabs */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Header
          title={
            <div className="border-b border-gray-200" value={activeTab} onChange={handleTabChange} variant="scrollable" scrollButtons="auto">
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Portfolio Risk" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Position Analysis" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Factor Attribution" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Stress Testing" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Risk Alerts" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Historical Trends" />
            </div>
          }
          action={
            <div  display="flex" gap={1}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" startIcon={<Settings />} onClick={() => setSettingsOpen(true)}>
                Settings
              </button>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" startIcon={<Download />}>
                Export
              </button>
            </div>
          }
        />

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
          <div className="grid" container spacing={3}>
            <div className="grid" item xs={12} md={6}>
              <div  variant="h6" gutterBottom>Risk Distribution</div>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={[
                      { name: 'Systematic Risk', value: 65, color: '#ff6b6b' },
                      { name: 'Idiosyncratic Risk', value: 25, color: '#4ecdc4' },
                      { name: 'Currency Risk', value: 5, color: '#45b7d1' },
                      { name: 'Other', value: 5, color: '#96ceb4' }
                    ]}
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value}%`}
                  >
                    {[
                      { name: 'Systematic Risk', value: 65, color: '#ff6b6b' },
                      { name: 'Idiosyncratic Risk', value: 25, color: '#4ecdc4' },
                      { name: 'Currency Risk', value: 5, color: '#45b7d1' },
                      { name: 'Other', value: 5, color: '#96ceb4' }
                    ].map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <RechartsTooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="grid" item xs={12} md={6}>
              <div  variant="h6" gutterBottom>Advanced Risk Metrics</div>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6}>
                  <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                    <div  variant="h4" color="primary.main">
                      {riskData?.portfolioMetrics.diversificationRatio.toFixed(2)}
                    </div>
                    <div  variant="caption">Diversification Ratio</div>
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                    <div  variant="h4" color="secondary.main">
                      {formatPercent(riskData?.portfolioMetrics.trackingError)}
                    </div>
                    <div  variant="caption">Tracking Error</div>
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                    <div  variant="h4" color="success.main">
                      {riskData?.portfolioMetrics.informationRatio.toFixed(2)}
                    </div>
                    <div  variant="caption">Information Ratio</div>
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                    <div  variant="h4" color="warning.main">
                      {riskData?.portfolioMetrics.calmarRatio.toFixed(2)}
                    </div>
                    <div  variant="caption">Calmar Ratio</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
          <div  variant="h6" gutterBottom>Individual Position Risk Analysis</div>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Weight</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Value</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">VaR (95%)</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Beta</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volatility</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Sharpe</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Risk Rating</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sector</td>
                </tr>
              </thead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                {riskData?.positions.map((position) => (
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={position.symbol} hover>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      <div  variant="body2" sx={{ fontWeight: 600 }}>
                        {position.symbol}
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatPercent(position.weight)}</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatCurrency(position.value)}</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  color="error.main" fontWeight="bold">
                        {formatCurrency(position.var95)}
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={position.beta.toFixed(2)} 
                        color={getRiskColor(Math.abs(position.beta - 1), { low: 0.2, medium: 0.5 })}
                        size="small"
                      />
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={formatPercent(position.volatility)} 
                        color={getRiskColor(position.volatility * 100, { low: 20, medium: 30 })}
                        size="small"
                      />
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  color={position.sharpe > 1 ? 'success.main' : 'warning.main'}>
                        {position.sharpe.toFixed(2)}
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={position.riskRating} 
                        color={position.riskRating === 'High' ? 'error' : position.riskRating === 'Medium' ? 'warning' : 'success'}
                        size="small"
                      />
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{position.sector}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
          <div  variant="h6" gutterBottom>Risk Factor Attribution</div>
          <div className="grid" container spacing={3}>
            <div className="grid" item xs={12} md={8}>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={riskData?.riskFactors}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                  <YAxis />
                  <RechartsTooltip />
                  <Bar dataKey="exposure" fill="#8884d8" name="Factor Exposure" />
                  <Bar dataKey="contribution" fill="#82ca9d" name="Risk Contribution" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="grid" item xs={12} md={4}>
              <div  variant="subtitle1" gutterBottom fontWeight="bold">
                Factor Analysis Summary
              </div>
              <List dense>
                {riskData?.riskFactors.map((factor, index) => (
                  <ListItem key={index}>
                    <ListItemIcon>
                      <Analytics color={Math.abs(factor.exposure) > 0.2 ? 'warning' : 'primary'} />
                    </ListItemIcon>
                    <ListItemText
                      primary={factor.name}
                      secondary={`Exposure: ${(factor.exposure * 100).toFixed(1)}%`}
                    />
                    <ListItemSecondaryAction>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={`${(factor.contribution * 100).toFixed(1)}%`}
                        size="small"
                        color={factor.contribution > 0.2 ? 'warning' : 'default'}
                      />
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
            </div>
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={3}>
          <div  variant="h6" gutterBottom>Stress Test Scenarios</div>
          <div className="grid" container spacing={3}>
            {riskData?.stressTests.map((test, index) => (
              <div className="grid" item xs={12} md={6} key={index}>
                <div className="bg-white shadow-md rounded-lg" variant="outlined" sx={{ height: '100%' }}>
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                      <div  variant="subtitle1" sx={{ fontWeight: 600 }}>
                        {test.name}
                      </div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={`${test.probability}% probability`}
                        size="small"
                        color={test.probability > 5 ? 'error' : test.probability > 2 ? 'warning' : 'default'}
                      />
                    </div>
                    
                    <div className="grid" container spacing={2}>
                      <div className="grid" item xs={6}>
                        <div  color="text.secondary" variant="caption">Market Drop</div>
                        <div  variant="h6" color="error.main" fontWeight="bold">
                          {test.marketDrop}%
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div  color="text.secondary" variant="caption">Portfolio Loss</div>
                        <div  variant="h6" color="error.main" fontWeight="bold">
                          {formatCurrency(test.portfolioLoss)}
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div  color="text.secondary" variant="caption">Expected Shortfall</div>
                        <div  variant="body2" fontWeight="bold">
                          {formatCurrency(test.expectedShortfall)}
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div  color="text.secondary" variant="caption">Worst Case</div>
                        <div  variant="body2" fontWeight="bold">
                          {formatCurrency(test.worstCase)}
                        </div>
                      </div>
                    </div>
                    
                    <div className="w-full bg-gray-200 rounded-full h-2" 
                      variant="determinate" 
                      value={Math.abs(test.portfolioLoss) / riskData.portfolioMetrics.totalValue * 100} 
                      color="error"
                      sx={{ mt: 2 }}
                    />
                    
                    <div  variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                      Time Horizon: {test.timeHorizon}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={4}>
          <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <div  variant="h6">Active Risk Alerts</div>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              variant="contained" 
              startIcon={<NotificationsActive />} 
              onClick={() => setAlertDialogOpen(true)}
            >
              Create Alert
            </button>
          </div>
          
          <div className="grid" container spacing={2}>
            {riskData?.riskAlerts.map((alert) => (
              <div className="grid" item xs={12} key={alert.id}>
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
                  severity={alert.severity} 
                  icon={getSeverityIcon(alert.severity)}
                  action={
                    <button className="p-2 rounded-full hover:bg-gray-100" color="inherit" size="small">
                      <Settings />
                    </button>
                  }
                >
                  <div>
                    <div  variant="subtitle2" fontWeight="bold">
                      {alert.symbol} - {alert.metric}
                    </div>
                    <div  variant="body2">
                      {alert.description}
                    </div>
                    <div  variant="body2" sx={{ mt: 1 }}>
                      <strong>Current:</strong> {typeof alert.value === 'number' ? 
                        (alert.value > 1000 ? formatCurrency(alert.value) : alert.value.toFixed(3)) : 
                        alert.value} | 
                      <strong> Threshold:</strong> {typeof alert.threshold === 'number' ? 
                        (alert.threshold > 1000 ? formatCurrency(alert.threshold) : alert.threshold.toFixed(3)) : 
                        alert.threshold}
                    </div>
                    <div  variant="caption" color="text.secondary">
                      {alert.timestamp.toLocaleString()} • Recommendation: {alert.recommendation}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={5}>
          <div  variant="h6" gutterBottom>Historical Risk Trends</div>
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={riskData?.historicalMetrics}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" />
              <RechartsTooltip 
                formatter={(value, name) => [
                  name.includes('var') || name.includes('cvar') ? formatCurrency(value) : 
                  name.includes('volatility') || name.includes('maxDD') ? formatPercent(value) :
                  value.toFixed(2), 
                  name
                ]} 
              />
              <Line yAxisId="left" type="monotone" dataKey="var95" stroke="#8884d8" name="VaR 95%" strokeWidth={2} />
              <Line yAxisId="left" type="monotone" dataKey="cvar95" stroke="#82ca9d" name="CVaR 95%" strokeWidth={2} />
              <Line yAxisId="right" type="monotone" dataKey="sharpe" stroke="#ffc658" name="Sharpe Ratio" strokeWidth={2} />
              <Line yAxisId="right" type="monotone" dataKey="volatility" stroke="#ff7300" name="Volatility" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Create Alert Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={alertDialogOpen} onClose={() => setAlertDialogOpen(false)} maxWidth="md" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Create Advanced Risk Alert</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div className="grid" container spacing={3} sx={{ mt: 1 }}>
            <div className="grid" item xs={12} sm={6}>
              <Autocomplete
                options={['PORTFOLIO', ...riskData?.positions.map(p => p.symbol) || []]}
                value={newAlert.symbol}
                onChange={(_, value) => setNewAlert({ ...newAlert, symbol: value || '' })}
                renderInput={(params) => (
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" {...params} label="Symbol" placeholder="e.g., AAPL or PORTFOLIO" />
                )}
              />
            </div>
            <div className="grid" item xs={12} sm={6}>
              <div className="mb-4" fullWidth>
                <label className="block text-sm font-medium text-gray-700 mb-1">Risk Metric</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={newAlert.metric}
                  onChange={(e) => setNewAlert({ ...newAlert, metric: e.target.value })}
                >
                  <option  value="var">Value at Risk</option>
                  <option  value="cvar">Expected Shortfall</option>
                  <option  value="volatility">Volatility</option>
                  <option  value="beta">Beta</option>
                  <option  value="correlation">Correlation</option>
                  <option  value="concentration">Concentration</option>
                  <option  value="drawdown">Max Drawdown</option>
                  <option  value="sharpe">Sharpe Ratio</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={4}>
              <div className="mb-4" fullWidth>
                <label className="block text-sm font-medium text-gray-700 mb-1">Condition</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={newAlert.condition}
                  onChange={(e) => setNewAlert({ ...newAlert, condition: e.target.value })}
                >
                  <option  value="above">Above</option>
                  <option  value="below">Below</option>
                  <option  value="change">% Change</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={4}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                label="Threshold"
                type="number"
                value={newAlert.threshold}
                onChange={(e) => setNewAlert({ ...newAlert, threshold: Number(e.target.value) })}
              />
            </div>
            <div className="grid" item xs={12} sm={4}>
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle"
                    checked={newAlert.enabled}
                    onChange={(e) => setNewAlert({ ...newAlert, enabled: e.target.checked })}
                  />
                }
                label="Enable Alert"
              />
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setAlertDialogOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleCreateAlert} variant="contained">Create Alert</button>
        </div>
      </div>

      {/* Settings Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={settingsOpen} onClose={() => setSettingsOpen(false)} maxWidth="md" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Risk Management Settings</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div  variant="h6" gutterBottom sx={{ mt: 2 }}>
            Alert Thresholds
          </div>
          <div className="grid" container spacing={3}>
            <div className="grid" item xs={12} sm={6}>
              <div  gutterBottom>Portfolio VaR Limit</div>
              <Slider
                value={alertThresholds.portfolioVaR}
                onChange={(_, value) => setAlertThresholds(prev => ({ ...prev, portfolioVaR: value }))}
                min={50000}
                max={200000}
                step={10000}
                valueLabelDisplay="auto"
                valueLabelFormat={(value) => formatCurrency(value)}
              />
            </div>
            <div className="grid" item xs={12} sm={6}>
              <div  gutterBottom>Concentration Limit</div>
              <Slider
                value={alertThresholds.concentrationLimit * 100}
                onChange={(_, value) => setAlertThresholds(prev => ({ ...prev, concentrationLimit: value / 100 }))}
                min={10}
                max={50}
                step={5}
                valueLabelDisplay="auto"
                valueLabelFormat={(value) => `${value}%`}
              />
            </div>
            <div className="grid" item xs={12} sm={6}>
              <div  gutterBottom>Volatility Limit</div>
              <Slider
                value={alertThresholds.volatilityLimit * 100}
                onChange={(_, value) => setAlertThresholds(prev => ({ ...prev, volatilityLimit: value / 100 }))}
                min={15}
                max={40}
                step={1}
                valueLabelDisplay="auto"
                valueLabelFormat={(value) => `${value}%`}
              />
            </div>
            <div className="grid" item xs={12} sm={6}>
              <div  gutterBottom>Beta Limit</div>
              <Slider
                value={alertThresholds.betaLimit}
                onChange={(_, value) => setAlertThresholds(prev => ({ ...prev, betaLimit: value }))}
                min={0.5}
                max={2.0}
                step={0.1}
                valueLabelDisplay="auto"
              />
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setSettingsOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setSettingsOpen(false)} variant="contained">Save Settings</button>
        </div>
      </div>
    </div>
  );
};

export default RiskManagement;