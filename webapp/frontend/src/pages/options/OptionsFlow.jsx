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
  Avatar
} from '@mui/material';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  ScatterChart,
  Scatter
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
  MonetizationOn,
  FlashOn,
  Whatshot,
  Public
} from '@mui/icons-material';

// Generate realistic options flow data
const generateOptionsFlow = () => {
  const flowData = [];
  const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ', 'IWM'];
  
  for (let i = 0; i < 50; i++) {
    const symbol = symbols[Math.floor(Math.random() * symbols.length)];
    const isCall = Math.random() > 0.5;
    const isUnusual = Math.random() > 0.85; // 15% chance of unusual activity
    const volume = Math.floor(Math.random() * 10000) + 100;
    const openInterest = Math.floor(Math.random() * 20000) + 500;
    const volumeOIRatio = volume / openInterest;
    
    const basePrice = 150;
    const strike = Math.round((basePrice + (Math.random() - 0.5) * 50) / 5) * 5;
    const premium = (0.5 + Math.random() * 10).toFixed(2);
    const size = volume * parseFloat(premium) * 100; // Notional size
    
    const time = new Date();
    time.setMinutes(time.getMinutes() - Math.floor(Math.random() * 480)); // Within last 8 hours
    
    flowData.push({
      id: i,
      symbol,
      type: isCall ? 'CALL' : 'PUT',
      strike,
      expiry: '2024-02-16',
      premium,
      volume: volume.toLocaleString(),
      openInterest: openInterest.toLocaleString(),
      volumeOIRatio: volumeOIRatio.toFixed(2),
      notionalSize: size,
      sentiment: volume > 1000 ? (isCall ? 'BULLISH' : 'BEARISH') : 'NEUTRAL',
      time: time.toLocaleTimeString(),
      isUnusual,
      flow: Math.random() > 0.5 ? 'BUY' : 'SELL',
      iv: (0.15 + Math.random() * 0.4).toFixed(3),
      delta: (Math.random() * 0.8).toFixed(3)
    });
  }
  
  return flowData.sort((a, b) => b.notionalSize - a.notionalSize);
};

// Calculate flow metrics
const calculateFlowMetrics = (flowData) => {
  const callFlow = flowData.filter(f => f.type === 'CALL');
  const putFlow = flowData.filter(f => f.type === 'PUT');
  
  const callVolume = callFlow.reduce((sum, f) => sum + parseInt(f.volume.replace(/,/g, '')), 0);
  const putVolume = putFlow.reduce((sum, f) => sum + parseInt(f.volume.replace(/,/g, '')), 0);
  
  const totalNotional = flowData.reduce((sum, f) => sum + f.notionalSize, 0);
  const unusualCount = flowData.filter(f => f.isUnusual).length;
  
  const topSymbols = {};
  flowData.forEach(f => {
    topSymbols[f.symbol] = (topSymbols[f.symbol] || 0) + f.notionalSize;
  });
  
  return {
    putCallRatio: (putVolume / callVolume).toFixed(2),
    totalVolume: (callVolume + putVolume).toLocaleString(),
    totalNotional: (totalNotional / 1000000).toFixed(1),
    unusualActivity: unusualCount,
    topSymbols: Object.entries(topSymbols)
      .sort(([,a], [,b]) => b - a)
      .slice(0, 5)
      .map(([symbol, notional]) => ({ symbol, notional: (notional / 1000000).toFixed(1) }))
  };
};

// Generate sector flow data
const generateSectorFlow = () => {
  const sectors = [
    { name: 'Technology', flow: 145.2, sentiment: 'BULLISH' },
    { name: 'Healthcare', flow: 89.7, sentiment: 'NEUTRAL' },
    { name: 'Financial', flow: 123.4, sentiment: 'BEARISH' },
    { name: 'Energy', flow: 67.3, sentiment: 'BULLISH' },
    { name: 'Consumer', flow: 98.1, sentiment: 'NEUTRAL' },
    { name: 'Industrial', flow: 76.8, sentiment: 'BEARISH' },
    { name: 'Materials', flow: 45.2, sentiment: 'NEUTRAL' },
    { name: 'Utilities', flow: 23.1, sentiment: 'BULLISH' }
  ];
  
  return sectors;
};

const OptionsFlow = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [flowData, setFlowData] = useState([]);
  const [flowMetrics, setFlowMetrics] = useState(null);
  const [sectorFlow, setSectorFlow] = useState([]);
  const [timeFilter, setTimeFilter] = useState('1H');
  const [sizeFilter, setSizeFilter] = useState(1000000); // $1M minimum
  const [symbolFilter, setSymbolFilter] = useState('ALL');
  
  const symbols = ['ALL', 'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ'];
  const timeFilters = ['15M', '1H', '4H', '1D'];
  
  useEffect(() => {
    loadFlowData();
    const interval = setInterval(loadFlowData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, [timeFilter, sizeFilter, symbolFilter]);
  
  const loadFlowData = () => {
    setLoading(true);
    
    try {
      let data = generateOptionsFlow();
      
      // Apply filters
      if (symbolFilter !== 'ALL') {
        data = data.filter(f => f.symbol === symbolFilter);
      }
      
      data = data.filter(f => f.notionalSize >= sizeFilter);
      
      const metrics = calculateFlowMetrics(data);
      const sectors = generateSectorFlow();
      
      setFlowData(data);
      setFlowMetrics(metrics);
      setSectorFlow(sectors);
      
    } catch (err) {
      setError('Failed to load options flow data');
    } finally {
      setLoading(false);
    }
  };
  
  const getSentimentColor = (sentiment) => {
    switch (sentiment) {
      case 'BULLISH': return 'success.main';
      case 'BEARISH': return 'error.main';
      default: return 'text.secondary';
    }
  };
  
  const getFlowColor = (flow) => {
    return flow === 'BUY' ? 'success.main' : 'error.main';
  };
  
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8'];
  
  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          Options Flow Analysis
        </div>
        <div  variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Real-time options order flow, unusual activity detection, and market sentiment analysis
        </div>
        <div  display="flex" gap={1} flexWrap="wrap">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Live Flow" color="primary" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Unusual Activity" color="success" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Sentiment Analysis" color="info" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Volume Analysis" color="warning" size="small" variant="outlined" />
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
                <label className="block text-sm font-medium text-gray-700 mb-1">Time Frame</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={timeFilter}
                  label="Time Frame"
                  onChange={(e) => setTimeFilter(e.target.value)}
                >
                  {timeFilters.map(time => (
                    <option  key={time} value={time}>{time}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Symbol</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={symbolFilter}
                  label="Symbol"
                  onChange={(e) => setSymbolFilter(e.target.value)}
                >
                  {symbols.map(symbol => (
                    <option  key={symbol} value={symbol}>{symbol}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Min Size ($M)"
                type="number"
                value={sizeFilter / 1000000}
                onChange={(e) => setSizeFilter(parseFloat(e.target.value) * 1000000)}
                size="small"
                fullWidth
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                startIcon={loading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} /> : <↻  />}
                onClick={loadFlowData}
                disabled={loading}
                fullWidth
              >
                Refresh
              </button>
            </div>
            <div className="grid" item xs={12} sm={4}>
              {flowMetrics && (
                <div  display="flex" gap={2}>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">P/C Ratio</div>
                    <div  variant="h6" fontWeight="bold">
                      {flowMetrics.putCallRatio}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Total Volume</div>
                    <div  variant="h6" fontWeight="bold">
                      {flowMetrics.totalVolume}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Unusual</div>
                    <div  variant="h6" fontWeight="bold" color="warning.main">
                      {flowMetrics.unusualActivity}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid" container spacing={3}>
        {/* Main Flow Table */}
        <div className="grid" item xs={12} lg={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header 
              title="Options Flow"
              subheader={`${flowData.length} transactions in last ${timeFilter}`}
              action={
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label="LIVE" 
                  color="success" 
                  size="small" 
                  icon={<FlashOn />}
                />
              }
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="border-b border-gray-200" value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 2 }}>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Flow Feed" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Unusual Activity" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Volume Leaders" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sector Flow" />
              </div>
              
              {activeTab === 0 && (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined" sx={{ maxHeight: 600 }}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Time</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Type</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Strike</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Premium</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Size ($M)</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Flow</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sentiment</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {flowData.slice(0, 50).map((flow) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={flow.id} hover sx={{ bgcolor: flow.isUnusual ? 'warning.light' : 'inherit' }}>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  variant="caption">{flow.time}</div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  variant="body2" fontWeight="bold">
                              {flow.symbol}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={flow.type} 
                              color={flow.type === 'CALL' ? 'success' : 'error'}
                              size="small"
                              variant="outlined"
                            />
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>${flow.strike}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${flow.premium}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{flow.volume}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2" fontWeight="bold">
                              ${(flow.notionalSize / 1000000).toFixed(1)}M
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={flow.flow} 
                              color={flow.flow === 'BUY' ? 'success' : 'error'}
                              size="small"
                            />
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  sx={{ color: getSentimentColor(flow.sentiment) }}>
                              {flow.sentiment}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              
              {activeTab === 1 && (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined" sx={{ maxHeight: 600 }}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Details</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Vol/OI</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Size</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Significance</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {flowData.filter(f => f.isUnusual).map((flow) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={flow.id} hover>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  display="flex" alignItems="center" gap={1}>
                              <Whatshot color="warning" fontSize="small" />
                              <div  variant="body2" fontWeight="bold">
                                {flow.symbol}
                              </div>
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  variant="body2">
                              {flow.type} ${flow.strike} {flow.expiry}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{flow.volume}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  
                              variant="body2" 
                              fontWeight="bold"
                              color={parseFloat(flow.volumeOIRatio) > 2 ? 'error.main' : 'text.primary'}
                            >
                              {flow.volumeOIRatio}x
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            ${(flow.notionalSize / 1000000).toFixed(1)}M
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label="HIGH" 
                              color="warning" 
                              size="small"
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              
              {activeTab === 2 && flowMetrics && (
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart data={flowMetrics.topSymbols}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" />
                    <YAxis label={{ value: 'Notional ($M)', angle: -90, position: 'insideLeft' }} />
                    <RechartsTooltip formatter={(value) => [`$${value}M`, 'Notional']} />
                    <Bar dataKey="notional" fill="#8884d8" />
                  </BarChart>
                </ResponsiveContainer>
              )}
              
              {activeTab === 3 && (
                <div className="grid" container spacing={3}>
                  <div className="grid" item xs={12} md={6}>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={sectorFlow}
                          cx="50%"
                          cy="50%"
                          outerRadius={100}
                          fill="#8884d8"
                          dataKey="flow"
                          label={({ name, value }) => `${name}: $${value}M`}
                        >
                          {sectorFlow.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <RechartsTooltip formatter={(value) => [`$${value}M`, 'Flow']} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="grid" item xs={12} md={6}>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sector</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Flow ($M)</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sentiment</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {sectorFlow.map((sector, index) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={sector.name}>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{sector.name}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${sector.flow}M</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <div  sx={{ color: getSentimentColor(sector.sentiment) }}>
                                  {sector.sentiment}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="grid" item xs={12} lg={4}>
          {/* Market Sentiment */}
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
            <div className="bg-white shadow-md rounded-lg"Header title="Market Sentiment" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6}>
                  <div  variant="caption" color="text.secondary">Overall</div>
                  <div  variant="h6" fontWeight="bold" color="success.main">
                    BULLISH
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="caption" color="text.secondary">Strength</div>
                  <div className="w-full bg-gray-200 rounded-full h-2" 
                    variant="determinate" 
                    value={72} 
                    color="success"
                    sx={{ mt: 1 }}
                  />
                </div>
                <div className="grid" item xs={12}>
                  <div  variant="caption" color="text.secondary">
                    Based on call/put flow analysis and unusual activity patterns
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Flow Indicators */}
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
            <div className="bg-white shadow-md rounded-lg"Header title="Flow Indicators" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6}>
                  <div  variant="caption" color="text.secondary">Call Flow</div>
                  <div  variant="h6" fontWeight="bold" color="success.main">
                    65%
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="caption" color="text.secondary">Put Flow</div>
                  <div  variant="h6" fontWeight="bold" color="error.main">
                    35%
                  </div>
                </div>
                <div className="grid" item xs={12}>
                  <div  variant="caption" color="text.secondary">Smart Money</div>
                  <div  variant="body2" fontWeight="bold">
                    Net Buying Calls
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Today's Highlights */}
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Today's Highlights" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div>
                <div  variant="subtitle2" gutterBottom>
                  🔥 Most Unusual Activity
                </div>
                <div  variant="body2" color="text.secondary" paragraph>
                  TSLA Feb 160 Calls - 15,000 contracts (10x normal volume)
                </div>
                
                <div  variant="subtitle2" gutterBottom>
                  📈 Largest Flow
                </div>
                <div  variant="body2" color="text.secondary" paragraph>
                  SPY Weekly Puts - $45M notional
                </div>
                
                <div  variant="subtitle2" gutterBottom>
                  ⚡ Hot Sectors
                </div>
                <div  variant="body2" color="text.secondary">
                  Technology (+$145M), Financial (-$123M)
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OptionsFlow;