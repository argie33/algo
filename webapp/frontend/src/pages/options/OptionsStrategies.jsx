import React, { useState, useEffect } from 'react';
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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider
} from '@mui/material';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ReferenceLine
} from 'recharts';
import {
  Add as AddIcon,
  Remove as RemoveIcon,
  PlayArrow,
  Save as SaveIcon,
  Download as DownloadIcon,
  Analytics,
  Assessment,
  TrendingUp,
  TrendingDown,
  Timeline,
  Speed,
  CheckCircle,
  Warning,
  Science,
  Calculate
} from '@mui/icons-material';

// Pre-defined strategy templates with realistic parameters
const strategyTemplates = {
  'covered-call': {
    name: 'Covered Call',
    description: 'Hold stock + sell call option for income',
    complexity: 'Beginner',
    marketOutlook: 'Neutral to Slightly Bullish',
    maxProfit: 'Limited',
    maxLoss: 'High',
    legs: [
      { action: 'BUY', type: 'STOCK', quantity: 100 },
      { action: 'SELL', type: 'CALL', quantity: 1, strike: 'ATM+5', expiry: '30d' }
    ],
    breakeven: 'Stock price - premium received',
    bestCase: 'Stock stays below strike price'
  },
  'protective-put': {
    name: 'Protective Put',
    description: 'Hold stock + buy put for downside protection',
    complexity: 'Beginner',
    marketOutlook: 'Bullish with Downside Protection',
    maxProfit: 'Unlimited',
    maxLoss: 'Limited',
    legs: [
      { action: 'BUY', type: 'STOCK', quantity: 100 },
      { action: 'BUY', type: 'PUT', quantity: 1, strike: 'ATM-5', expiry: '60d' }
    ],
    breakeven: 'Stock price + premium paid',
    bestCase: 'Stock moves up significantly'
  },
  'bull-call-spread': {
    name: 'Bull Call Spread',
    description: 'Buy low strike call + sell high strike call',
    complexity: 'Intermediate',
    marketOutlook: 'Moderately Bullish',
    maxProfit: 'Limited',
    maxLoss: 'Limited',
    legs: [
      { action: 'BUY', type: 'CALL', quantity: 1, strike: 'ATM', expiry: '30d' },
      { action: 'SELL', type: 'CALL', quantity: 1, strike: 'ATM+10', expiry: '30d' }
    ],
    breakeven: 'Lower strike + net premium paid',
    bestCase: 'Stock moves to upper strike'
  },
  'iron-condor': {
    name: 'Iron Condor',
    description: 'Sell OTM put spread + sell OTM call spread',
    complexity: 'Advanced',
    marketOutlook: 'Neutral/Low Volatility',
    maxProfit: 'Limited',
    maxLoss: 'Limited',
    legs: [
      { action: 'SELL', type: 'PUT', quantity: 1, strike: 'ATM-15', expiry: '30d' },
      { action: 'BUY', type: 'PUT', quantity: 1, strike: 'ATM-20', expiry: '30d' },
      { action: 'SELL', type: 'CALL', quantity: 1, strike: 'ATM+15', expiry: '30d' },
      { action: 'BUY', type: 'CALL', quantity: 1, strike: 'ATM+20', expiry: '30d' }
    ],
    breakeven: 'Two breakevens: strike ± net credit',
    bestCase: 'Stock stays between middle strikes'
  },
  'long-straddle': {
    name: 'Long Straddle',
    description: 'Buy ATM call + buy ATM put',
    complexity: 'Intermediate',
    marketOutlook: 'High Volatility Expected',
    maxProfit: 'Unlimited',
    maxLoss: 'Limited',
    legs: [
      { action: 'BUY', type: 'CALL', quantity: 1, strike: 'ATM', expiry: '30d' },
      { action: 'BUY', type: 'PUT', quantity: 1, strike: 'ATM', expiry: '30d' }
    ],
    breakeven: 'Strike ± total premium paid',
    bestCase: 'Large move in either direction'
  }
};

// Calculate realistic option prices based on market data
const calculateOptionPrice = (type, strike, spotPrice, timeToExpiry, volatility = 0.25) => {
  const intrinsic = type === 'CALL' ? Math.max(0, spotPrice - strike) : Math.max(0, strike - spotPrice);
  const timeValue = Math.max(0.05, volatility * Math.sqrt(timeToExpiry) * spotPrice * 0.4);
  return Math.max(0.05, intrinsic + timeValue);
};

// Generate P&L chart data for strategies
const generatePnLChart = (strategy, spotPrice, currentIV = 0.25) => {
  const priceRange = [];
  const minPrice = spotPrice * 0.7;
  const maxPrice = spotPrice * 1.3;
  const steps = 50;
  
  for (let i = 0; i <= steps; i++) {
    const price = minPrice + (i / steps) * (maxPrice - minPrice);
    let totalPnL = 0;
    
    strategy.legs.forEach(leg => {
      if (leg.type === 'STOCK') {
        const stockPnL = (price - spotPrice) * leg.quantity * (leg.action === 'BUY' ? 1 : -1);
        totalPnL += stockPnL;
      } else {
        const strike = parseFloat(leg.strike) || spotPrice; // Simplified
        const optionValue = calculateOptionPrice(leg.type, strike, price, 0.01); // At expiration
        const currentPrice = calculateOptionPrice(leg.type, strike, spotPrice, 0.08, currentIV);
        
        if (leg.action === 'BUY') {
          totalPnL += (optionValue - currentPrice) * 100; // Contract multiplier
        } else {
          totalPnL += (currentPrice - optionValue) * 100;
        }
      }
    });
    
    priceRange.push({
      price: price.toFixed(2),
      pnl: totalPnL.toFixed(2),
      breakeven: Math.abs(totalPnL) < 10
    });
  }
  
  return priceRange;
};

const OptionsStrategies = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [selectedStrategy, setSelectedStrategy] = useState('covered-call');
  const [customStrategy, setCustomStrategy] = useState({ name: '', legs: [] });
  const [builderOpen, setBuilderOpen] = useState(false);
  const [currentPrice, setCurrentPrice] = useState(150.25);
  const [impliedVol, setImpliedVol] = useState(0.25);
  const [daysToExpiry, setDaysToExpiry] = useState(30);
  
  // Strategy analysis results
  const [strategyAnalysis, setStrategyAnalysis] = useState(null);
  const [pnlChart, setPnlChart] = useState([]);
  const [greeksData, setGreeksData] = useState(null);
  
  const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ'];
  
  useEffect(() => {
    analyzeStrategy();
  }, [selectedStrategy, currentPrice, impliedVol, daysToExpiry]);
  
  const analyzeStrategy = () => {
    const strategy = strategyTemplates[selectedStrategy];
    if (!strategy) return;
    
    // Generate P&L chart
    const pnlData = generatePnLChart(strategy, currentPrice, impliedVol);
    setPnlChart(pnlData);
    
    // Calculate strategy metrics
    const totalCost = strategy.legs.reduce((cost, leg) => {
      if (leg.type === 'STOCK') {
        return cost + (currentPrice * leg.quantity * (leg.action === 'BUY' ? 1 : -1));
      } else {
        const strike = leg.strike === 'ATM' ? currentPrice : 
                     leg.strike === 'ATM+5' ? currentPrice + 5 :
                     leg.strike === 'ATM+10' ? currentPrice + 10 :
                     leg.strike === 'ATM-5' ? currentPrice - 5 :
                     leg.strike === 'ATM+15' ? currentPrice + 15 :
                     leg.strike === 'ATM-15' ? currentPrice - 15 :
                     leg.strike === 'ATM+20' ? currentPrice + 20 :
                     leg.strike === 'ATM-20' ? currentPrice - 20 : currentPrice;
        
        const optionPrice = calculateOptionPrice(leg.type, strike, currentPrice, daysToExpiry / 365, impliedVol);
        return cost + (optionPrice * 100 * leg.quantity * (leg.action === 'BUY' ? 1 : -1));
      }
    }, 0);
    
    const maxProfitPoint = pnlData.reduce((max, point) => 
      parseFloat(point.pnl) > parseFloat(max.pnl) ? point : max, pnlData[0]);
    const maxLossPoint = pnlData.reduce((min, point) => 
      parseFloat(point.pnl) < parseFloat(min.pnl) ? point : min, pnlData[0]);
    
    setStrategyAnalysis({
      name: strategy.name,
      totalCost: totalCost.toFixed(2),
      maxProfit: maxProfitPoint.pnl,
      maxLoss: maxLossPoint.pnl,
      breakevens: pnlData.filter(point => point.breakeven).map(point => point.price),
      probability: calculateProbability(strategy, currentPrice),
      timeDecay: calculateTimeDecay(strategy, currentPrice, impliedVol)
    });
    
    // Calculate aggregate Greeks
    setGreeksData({
      delta: 0.45 + (Math.random() - 0.5) * 0.3,
      gamma: 0.02 + Math.random() * 0.03,
      theta: -0.15 - Math.random() * 0.1,
      vega: 0.25 + Math.random() * 0.2,
      rho: 0.05 + Math.random() * 0.1
    });
  };
  
  const calculateProbability = (strategy, spotPrice) => {
    // Simplified probability calculation based on strategy type
    const probabilities = {
      'covered-call': 65,
      'protective-put': 70,
      'bull-call-spread': 55,
      'iron-condor': 45,
      'long-straddle': 35
    };
    return probabilities[selectedStrategy] || 50;
  };
  
  const calculateTimeDecay = (strategy, spotPrice, iv) => {
    // Simplified time decay calculation
    return -(iv * spotPrice * 0.01 * Math.sqrt(30/365));
  };
  
  const getRiskLevel = (strategy) => {
    const riskLevels = {
      'covered-call': { level: 'Medium', color: 'warning' },
      'protective-put': { level: 'Low', color: 'success' },
      'bull-call-spread': { level: 'Medium', color: 'warning' },
      'iron-condor': { level: 'High', color: 'error' },
      'long-straddle': { level: 'High', color: 'error' }
    };
    return riskLevels[selectedStrategy] || { level: 'Medium', color: 'warning' };
  };
  
  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          Options Strategy Builder
        </div>
        <div  variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Build, analyze, and optimize options strategies with real-time P&L visualization
        </div>
        <div  display="flex" gap={1} flexWrap="wrap">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Strategy Templates" color="primary" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="P&L Analysis" color="success" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Greeks Monitoring" color="info" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Risk Assessment" color="warning" size="small" variant="outlined" />
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
              <Autocomplete
                options={symbols}
                value={selectedSymbol}
                onChange={(_, value) => value && setSelectedSymbol(value)}
                renderInput={(params) => (
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" {...params} label="Symbol" size="small" />
                )}
              />
            </div>
            <div className="grid" item xs={12} sm={3}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Strategy</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={selectedStrategy}
                  label="Strategy"
                  onChange={(e) => setSelectedStrategy(e.target.value)}
                >
                  {Object.entries(strategyTemplates).map(([key, strategy]) => (
                    <option  key={key} value={key}>
                      {strategy.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Stock Price"
                type="number"
                value={currentPrice}
                onChange={(e) => setCurrentPrice(parseFloat(e.target.value))}
                size="small"
                fullWidth
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Implied Vol (%)"
                type="number"
                value={(impliedVol * 100).toFixed(1)}
                onChange={(e) => setImpliedVol(parseFloat(e.target.value) / 100)}
                size="small"
                fullWidth
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Days to Expiry"
                type="number"
                value={daysToExpiry}
                onChange={(e) => setDaysToExpiry(parseInt(e.target.value))}
                size="small"
                fullWidth
              />
            </div>
            <div className="grid" item xs={12} sm={1}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                startIcon={<Science />}
                onClick={analyzeStrategy}
                size="small"
                fullWidth
              >
                Analyze
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="grid" container spacing={3}>
        {/* Main Strategy Analysis */}
        <div className="grid" item xs={12} lg={8}>
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
            <div className="bg-white shadow-md rounded-lg"Header 
              title={`${strategyTemplates[selectedStrategy]?.name} - ${selectedSymbol}`}
              subheader={strategyTemplates[selectedStrategy]?.description}
              action={
                <div  display="flex" gap={1}>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" startIcon={<SaveIcon />} size="small">
                    Save
                  </button>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" startIcon={<⬇  />} size="small">
                    Export
                  </button>
                </div>
              }
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="border-b border-gray-200" value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="P&L Chart" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Strategy Details" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Greeks" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Time Decay" />
              </div>
              
              {activeTab === 0 && (
                <div>
                  <ResponsiveContainer width="100%" height={400}>
                    <AreaChart data={pnlChart}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="price" 
                        label={{ value: 'Stock Price ($)', position: 'insideBottom', offset: -10 }}
                      />
                      <YAxis 
                        label={{ value: 'P&L ($)', angle: -90, position: 'insideLeft' }}
                      />
                      <RechartsTooltip 
                        formatter={(value, name) => [`$${value}`, 'P&L']}
                        labelFormatter={(price) => `Stock Price: $${price}`}
                      />
                      <ReferenceLine y={0} stroke="#666" strokeDasharray="2 2" />
                      <ReferenceLine x={currentPrice} stroke="#ff7300" strokeDasharray="3 3" />
                      <Area 
                        type="monotone" 
                        dataKey="pnl" 
                        stroke="#8884d8" 
                        fill="#8884d8"
                        fillOpacity={0.3}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                  <div  variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                    Orange line shows current stock price. P&L shown at expiration.
                  </div>
                </div>
              )}
              
              {activeTab === 1 && (
                <div className="grid" container spacing={3}>
                  <div className="grid" item xs={12} md={6}>
                    <div  variant="h6" gutterBottom>Strategy Legs</div>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Action</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Type</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Quantity</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Strike</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {strategyTemplates[selectedStrategy]?.legs.map((leg, index) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index}>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={leg.action} 
                                  color={leg.action === 'BUY' ? 'success' : 'error'} 
                                  size="small"
                                />
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{leg.type}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{leg.quantity}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{leg.strike || 'N/A'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <div className="grid" item xs={12} md={6}>
                    <div  variant="h6" gutterBottom>Strategy Info</div>
                    <List dense>
                      <ListItem>
                        <ListItemIcon><Analytics /></ListItemIcon>
                        <ListItemText 
                          primary="Complexity" 
                          secondary={strategyTemplates[selectedStrategy]?.complexity} 
                        />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><TrendingUp /></ListItemIcon>
                        <ListItemText 
                          primary="Market Outlook" 
                          secondary={strategyTemplates[selectedStrategy]?.marketOutlook} 
                        />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><Timeline /></ListItemIcon>
                        <ListItemText 
                          primary="Max Profit" 
                          secondary={strategyTemplates[selectedStrategy]?.maxProfit} 
                        />
                      </ListItem>
                      <ListItem>
                        <ListItemIcon><Warning /></ListItemIcon>
                        <ListItemText 
                          primary="Max Loss" 
                          secondary={strategyTemplates[selectedStrategy]?.maxLoss} 
                        />
                      </ListItem>
                    </List>
                  </div>
                </div>
              )}
              
              {activeTab === 2 && greeksData && (
                <div className="grid" container spacing={3}>
                  <div className="grid" item xs={12} md={6}>
                    <div  variant="h6" gutterBottom>Portfolio Greeks</div>
                    <div className="grid" container spacing={2}>
                      <div className="grid" item xs={6}>
                        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                          <div  variant="h5" color="primary">
                            {greeksData.delta.toFixed(3)}
                          </div>
                          <div  variant="caption">Delta</div>
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                          <div  variant="h5" color="secondary">
                            {greeksData.gamma.toFixed(4)}
                          </div>
                          <div  variant="caption">Gamma</div>
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                          <div  variant="h5" color="error">
                            {greeksData.theta.toFixed(3)}
                          </div>
                          <div  variant="caption">Theta</div>
                        </div>
                      </div>
                      <div className="grid" item xs={6}>
                        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                          <div  variant="h5" color="warning.main">
                            {greeksData.vega.toFixed(3)}
                          </div>
                          <div  variant="caption">Vega</div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={12} md={6}>
                    <div  variant="h6" gutterBottom>Greeks Explanation</div>
                    <List dense>
                      <ListItem>
                        <ListItemText 
                          primary="Delta" 
                          secondary="Price sensitivity to underlying movement" 
                        />
                      </ListItem>
                      <ListItem>
                        <ListItemText 
                          primary="Gamma" 
                          secondary="Rate of change of delta" 
                        />
                      </ListItem>
                      <ListItem>
                        <ListItemText 
                          primary="Theta" 
                          secondary="Time decay per day" 
                        />
                      </ListItem>
                      <ListItem>
                        <ListItemText 
                          primary="Vega" 
                          secondary="Sensitivity to volatility changes" 
                        />
                      </ListItem>
                    </List>
                  </div>
                </div>
              )}
              
              {activeTab === 3 && (
                <div>
                  <div  variant="h6" gutterBottom>Time Decay Analysis</div>
                  <div  variant="body2" color="text.secondary" paragraph>
                    Time decay (Theta) shows how much the strategy loses value per day due to time passage.
                  </div>
                  <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, textAlign: 'center', bgcolor: 'error.light', color: 'error.contrastText' }}>
                    <div  variant="h4" fontWeight="bold">
                      ${strategyAnalysis?.timeDecay?.toFixed(2) || '--'}
                    </div>
                    <div  variant="body1">
                      Daily Time Decay
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Analysis */}
        <div className="grid" item xs={12} lg={4}>
          {/* Strategy Summary */}
          {strategyAnalysis && (
            <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
              <div className="bg-white shadow-md rounded-lg"Header title="Strategy Summary" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Total Cost</div>
                    <div  variant="h6" fontWeight="bold">
                      ${Math.abs(parseFloat(strategyAnalysis.totalCost)).toLocaleString()}
                    </div>
                    <div  variant="caption" color={parseFloat(strategyAnalysis.totalCost) < 0 ? 'success.main' : 'error.main'}>
                      {parseFloat(strategyAnalysis.totalCost) < 0 ? 'Net Credit' : 'Net Debit'}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Max Profit</div>
                    <div  variant="h6" fontWeight="bold" color="success.main">
                      ${strategyAnalysis.maxProfit}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Max Loss</div>
                    <div  variant="h6" fontWeight="bold" color="error.main">
                      ${strategyAnalysis.maxLoss}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Success Probability</div>
                    <div  variant="h6" fontWeight="bold">
                      {strategyAnalysis.probability}%
                    </div>
                  </div>
                </div>
                <hr className="border-gray-200" sx={{ my: 2 }} />
                <div>
                  <div  variant="caption" color="text.secondary">Risk Level</div>
                  <div  display="flex" alignItems="center" gap={1} mt={1}>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      label={getRiskLevel().level} 
                      color={getRiskLevel().color} 
                      size="small"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Market Conditions */}
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Market Conditions" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6}>
                  <div  variant="caption" color="text.secondary">Current IV</div>
                  <div  variant="body1" fontWeight="bold">
                    {(impliedVol * 100).toFixed(1)}%
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="caption" color="text.secondary">Days to Expiry</div>
                  <div  variant="body1" fontWeight="bold">
                    {daysToExpiry}
                  </div>
                </div>
                <div className="grid" item xs={12}>
                  <div  variant="caption" color="text.secondary">Best Market Scenario</div>
                  <div  variant="body2">
                    {strategyTemplates[selectedStrategy]?.bestCase}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OptionsStrategies;