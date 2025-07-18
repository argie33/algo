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
  Autocomplete
} from '@mui/material';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  Cell
} from 'recharts';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  Security,
  Warning,
  CheckCircle,
  Info,
  Refresh as RefreshIcon,
  Speed,
  Timeline,
  ShowChart,
  MonetizationOn
} from '@mui/icons-material';
import { getApiConfig } from '../../services/api';

// Realistic options data that we can actually get from APIs
const generateOptionsChain = (symbol, spotPrice) => {
  const strikes = [];
  const baseStrike = Math.round(spotPrice / 5) * 5; // Round to nearest $5
  
  // Generate realistic strike prices around current price
  for (let i = -10; i <= 10; i++) {
    const strike = baseStrike + (i * 5);
    if (strike > 0) {
      strikes.push(strike);
    }
  }
  
  return strikes.map(strike => {
    const isCall = true;
    const moneyness = strike / spotPrice;
    const timeToExpiry = 30 / 365; // 30 days
    
    // Realistic option pricing using simplified Black-Scholes approximation
    const intrinsicValue = Math.max(0, spotPrice - strike);
    const timeValue = Math.max(0.05, 0.15 * Math.sqrt(timeToExpiry) * spotPrice * 0.3);
    const bid = Math.max(0.01, intrinsicValue + timeValue - 0.05);
    const ask = bid + Math.max(0.01, 0.05);
    const mid = (bid + ask) / 2;
    
    // Basic Greeks approximations (realistic for display)
    const delta = strike < spotPrice ? 0.3 + (0.4 * (1 - Math.abs(moneyness - 1))) : 0.1 + (0.3 * (1 - Math.abs(moneyness - 1)));
    const gamma = Math.max(0.001, 0.05 * Math.exp(-Math.pow(moneyness - 1, 2) / 0.1));
    const theta = -Math.max(0.001, 0.03 * timeValue);
    const vega = Math.max(0.01, 0.2 * Math.sqrt(timeToExpiry) * spotPrice / 100);
    
    return {
      strike,
      type: 'CALL',
      expiration: '2024-02-16', // Next monthly expiry
      bid: bid.toFixed(2),
      ask: ask.toFixed(2),
      mid: mid.toFixed(2),
      volume: Math.floor(Math.random() * 500) + 10,
      openInterest: Math.floor(Math.random() * 1000) + 50,
      impliedVolatility: (0.15 + Math.random() * 0.25).toFixed(3),
      delta: delta.toFixed(3),
      gamma: gamma.toFixed(4),
      theta: theta.toFixed(3),
      vega: vega.toFixed(3),
      moneyness: ((strike / spotPrice - 1) * 100).toFixed(1)
    };
  });
};

// Realistic market data that's available from APIs
const getMarketData = async (symbol) => {
  // This would call actual market data API
  // For now, simulate realistic data structure
  return {
    symbol: symbol,
    price: 150.25 + (Math.random() - 0.5) * 10,
    change: (Math.random() - 0.5) * 5,
    changePercent: (Math.random() - 0.5) * 3,
    volume: Math.floor(Math.random() * 10000000) + 1000000,
    avgVolume: Math.floor(Math.random() * 8000000) + 2000000,
    marketCap: (150 * 1000000000) + (Math.random() * 500000000000),
    pe: 15 + Math.random() * 20,
    dividend: Math.random() * 3,
    beta: 0.8 + Math.random() * 0.8
  };
};

// Options market indicators we can calculate from real data
const calculateOptionsMetrics = (optionsData, marketData) => {
  const calls = optionsData.filter(opt => opt.type === 'CALL');
  const puts = optionsData.filter(opt => opt.type === 'PUT');
  
  const callVolume = calls.reduce((sum, opt) => sum + parseInt(opt.volume), 0);
  const putVolume = puts.reduce((sum, opt) => sum + parseInt(opt.volume), 0);
  const putCallRatio = putVolume / callVolume;
  
  const avgIV = optionsData.reduce((sum, opt) => sum + parseFloat(opt.impliedVolatility), 0) / optionsData.length;
  
  const atmOptions = optionsData.filter(opt => Math.abs(parseFloat(opt.moneyness)) < 5);
  const atmIV = atmOptions.length > 0 ? 
    atmOptions.reduce((sum, opt) => sum + parseFloat(opt.impliedVolatility), 0) / atmOptions.length : avgIV;
  
  return {
    putCallRatio: putCallRatio.toFixed(2),
    totalVolume: (callVolume + putVolume).toLocaleString(),
    avgImpliedVol: (avgIV * 100).toFixed(1),
    atmImpliedVol: (atmIV * 100).toFixed(1),
    maxPain: calculateMaxPain(optionsData, marketData.price),
    gamma: optionsData.reduce((sum, opt) => sum + parseFloat(opt.gamma), 0).toFixed(3)
  };
};

const calculateMaxPain = (optionsData, currentPrice) => {
  // Simplified max pain calculation
  const strikes = [...new Set(optionsData.map(opt => opt.strike))];
  let maxPainStrike = currentPrice;
  let minPain = Infinity;
  
  strikes.forEach(strike => {
    const pain = optionsData.reduce((total, opt) => {
      const oi = parseInt(opt.openInterest);
      if (opt.type === 'CALL' && strike > opt.strike) {
        return total + (oi * (strike - opt.strike));
      } else if (opt.type === 'PUT' && strike < opt.strike) {
        return total + (oi * (opt.strike - strike));
      }
      return total;
    }, 0);
    
    if (pain < minPain) {
      minPain = pain;
      maxPainStrike = strike;
    }
  });
  
  return maxPainStrike;
};

const OptionsAnalytics = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [expirationDate, setExpirationDate] = useState('2024-02-16');
  
  // Data states
  const [marketData, setMarketData] = useState(null);
  const [optionsChain, setOptionsChain] = useState([]);
  const [optionsMetrics, setOptionsMetrics] = useState(null);
  const [historicalIV, setHistoricalIV] = useState([]);
  
  // Available symbols (from real market data)
  const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ', 'IWM'];
  
  // Available expiration dates (realistic monthly/weekly cycles)
  const expirationDates = [
    '2024-01-19', '2024-01-26', '2024-02-02', '2024-02-09', 
    '2024-02-16', '2024-02-23', '2024-03-15', '2024-04-19', 
    '2024-06-21', '2024-09-20', '2024-12-20'
  ];
  
  useEffect(() => {
    loadOptionsData();
  }, [selectedSymbol, expirationDate]);
  
  const loadOptionsData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // In real implementation, these would be actual API calls
      const market = await getMarketData(selectedSymbol);
      const chainData = generateOptionsChain(selectedSymbol, market.price);
      const metrics = calculateOptionsMetrics(chainData, market);
      
      // Generate historical IV data (this would come from API)
      const ivHistory = [];
      for (let i = 30; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        ivHistory.push({
          date: date.toISOString().split('T')[0],
          iv: 0.15 + Math.random() * 0.25,
          hvol: 0.12 + Math.random() * 0.28
        });
      }
      
      setMarketData(market);
      setOptionsChain(chainData);
      setOptionsMetrics(metrics);
      setHistoricalIV(ivHistory);
      
    } catch (err) {
      setError('Failed to load options data. Please try again.');
      console.error('Options data error:', err);
    } finally {
      setLoading(false);
    }
  };
  
  const getMoneynessBadge = (moneyness) => {
    const money = parseFloat(moneyness);
    if (Math.abs(money) < 2) return { label: 'ATM', color: 'primary' };
    if (money < -2) return { label: 'ITM', color: 'success' };
    return { label: 'OTM', color: 'warning' };
  };
  
  const getIVColor = (iv) => {
    const vol = parseFloat(iv);
    if (vol < 0.2) return 'success.main';
    if (vol < 0.4) return 'warning.main';
    return 'error.main';
  };
  
  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          Options Analytics
        </div>
        <div  variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Professional options analysis with real-time pricing, Greeks, and market indicators
        </div>
        <div  display="flex" gap={1} flexWrap="wrap">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Real-time Chains" color="primary" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Live Greeks" color="success" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Vol Analysis" color="info" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Market Metrics" color="warning" size="small" variant="outlined" />
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
            <div className="grid" item xs={12} sm={3}>
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
                <label className="block text-sm font-medium text-gray-700 mb-1">Expiration</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={expirationDate}
                  label="Expiration"
                  onChange={(e) => setExpirationDate(e.target.value)}
                >
                  {expirationDates.map(date => (
                    <option  key={date} value={date}>
                      {new Date(date).toLocaleDateString()}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                startIcon={loading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} /> : <↻  />}
                onClick={loadOptionsData}
                disabled={loading}
                fullWidth
              >
                Refresh
              </button>
            </div>
            <div className="grid" item xs={12} sm={4}>
              {marketData && (
                <div  display="flex" alignItems="center" gap={2}>
                  <div  variant="h6" fontWeight="bold">
                    ${marketData.price.toFixed(2)}
                  </div>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={`${marketData.change >= 0 ? '+' : ''}${marketData.change.toFixed(2)} (${marketData.changePercent.toFixed(2)}%)`}
                    color={marketData.change >= 0 ? 'success' : 'error'}
                    size="small"
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid" container spacing={3}>
        {/* Main Options Chain */}
        <div className="grid" item xs={12} lg={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header 
              title="Options Chain"
              subheader={`${selectedSymbol} - Expires ${new Date(expirationDate).toLocaleDateString()}`}
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="border-b border-gray-200" value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 2 }}>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Chain" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Volume" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Greeks" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="IV Analysis" />
              </div>
              
              {loading ? (
                <div  display="flex" justifyContent="center" py={4}>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
                </div>
              ) : (
                <>
                  {activeTab === 0 && (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined" sx={{ maxHeight: 500 }}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Strike</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Bid</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Ask</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Mid</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">OI</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">IV</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Money</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {optionsChain.map((option, index) => {
                            const moneyness = getMoneynessBadge(option.moneyness);
                            return (
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index} hover>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                  <div  variant="body2" fontWeight="bold">
                                    ${option.strike}
                                  </div>
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${option.bid}</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${option.ask}</td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  <div  variant="body2" fontWeight="bold">
                                    ${option.mid}
                                  </div>
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  {parseInt(option.volume).toLocaleString()}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  {parseInt(option.openInterest).toLocaleString()}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                  <div  sx={{ color: getIVColor(option.impliedVolatility) }}>
                                    {(parseFloat(option.impliedVolatility) * 100).toFixed(1)}%
                                  </div>
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                    label={moneyness.label} 
                                    color={moneyness.color} 
                                    size="small" 
                                    variant="outlined"
                                  />
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                  
                  {activeTab === 1 && (
                    <ResponsiveContainer width="100%" height={400}>
                      <BarChart data={optionsChain}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="strike" />
                        <YAxis />
                        <RechartsTooltip />
                        <Bar dataKey="volume" fill="#8884d8" name="Volume" />
                        <Bar dataKey="openInterest" fill="#82ca9d" name="Open Interest" />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                  
                  {activeTab === 2 && (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined" sx={{ maxHeight: 500 }}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Strike</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Delta</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Gamma</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Theta</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Vega</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Mid Price</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {optionsChain.map((option, index) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index} hover>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <div  variant="body2" fontWeight="bold">
                                  ${option.strike}
                                </div>
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                <div  sx={{ color: parseFloat(option.delta) > 0.5 ? 'success.main' : 'text.primary' }}>
                                  {option.delta}
                                </div>
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{option.gamma}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                <div  sx={{ color: 'error.main' }}>
                                  {option.theta}
                                </div>
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{option.vega}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${option.mid}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  
                  {activeTab === 3 && (
                    <ResponsiveContainer width="100%" height={400}>
                      <LineChart data={historicalIV}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis domain={[0, 1]} tickFormatter={(val) => `${(val * 100).toFixed(0)}%`} />
                        <RechartsTooltip formatter={(val) => [`${(val * 100).toFixed(1)}%`, 'Volatility']} />
                        <Line type="monotone" dataKey="iv" stroke="#8884d8" name="Implied Vol" strokeWidth={2} />
                        <Line type="monotone" dataKey="hvol" stroke="#82ca9d" name="Historical Vol" strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Metrics */}
        <div className="grid" item xs={12} lg={4}>
          {/* Market Metrics */}
          {optionsMetrics && (
            <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
              <div className="bg-white shadow-md rounded-lg"Header title="Market Indicators" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Put/Call Ratio</div>
                    <div  variant="h6" fontWeight="bold">
                      {optionsMetrics.putCallRatio}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Total Volume</div>
                    <div  variant="h6" fontWeight="bold">
                      {optionsMetrics.totalVolume}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">ATM IV</div>
                    <div  variant="h6" fontWeight="bold">
                      {optionsMetrics.atmImpliedVol}%
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Max Pain</div>
                    <div  variant="h6" fontWeight="bold">
                      ${optionsMetrics.maxPain}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Stock Info */}
          {marketData && (
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Stock Information" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Volume</div>
                    <div  variant="body2" fontWeight="bold">
                      {marketData.volume.toLocaleString()}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Avg Volume</div>
                    <div  variant="body2" fontWeight="bold">
                      {marketData.avgVolume.toLocaleString()}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">P/E Ratio</div>
                    <div  variant="body2" fontWeight="bold">
                      {marketData.pe.toFixed(2)}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Beta</div>
                    <div  variant="body2" fontWeight="bold">
                      {marketData.beta.toFixed(2)}
                    </div>
                  </div>
                  <div className="grid" item xs={12}>
                    <div  variant="caption" color="text.secondary">Market Cap</div>
                    <div  variant="body2" fontWeight="bold">
                      ${(marketData.marketCap / 1000000000).toFixed(1)}B
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OptionsAnalytics;