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
  Slider,
  Chip,
  Tabs,
  Tab,
  Switch,
  FormControlLabel,
  Tooltip,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Autocomplete,
  Divider
} from '@mui/material';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell
} from 'recharts';
import {
  ShowChart,
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  Timeline,
  Speed,
  Refresh as RefreshIcon,
  Download as DownloadIcon,
  Save as SaveIcon,
  ViewInAr,
  Grain,
  Whatshot,
  FlashOn,
  Psychology,
  Warning,
  Science
} from '@mui/icons-material';

// Generate realistic volatility surface data
const generateVolatilitySurface = (symbol, spotPrice) => {
  const surfaceData = [];
  const strikes = [];
  const expiries = [7, 14, 30, 60, 90, 180, 365]; // Days to expiration
  
  // Generate strikes around current price
  for (let i = -20; i <= 20; i += 2.5) {
    const strike = spotPrice * (1 + i / 100);
    if (strike > 0) strikes.push(strike);
  }
  
  strikes.forEach(strike => {
    expiries.forEach(dte => {
      const moneyness = strike / spotPrice;
      const timeToExpiry = dte / 365;
      
      // Realistic IV surface modeling
      // Higher IV for OTM options and shorter expiries
      const atmVol = 0.20 + Math.random() * 0.1; // Base ATM volatility
      const skewEffect = Math.abs(moneyness - 1) * 0.3; // Volatility skew
      const termStructure = Math.max(0.05, 0.8 - Math.sqrt(timeToExpiry) * 0.2); // Term structure
      const smileEffect = Math.pow(Math.abs(moneyness - 1), 2) * 0.15; // Volatility smile
      
      const impliedVol = Math.max(0.05, 
        atmVol + skewEffect + smileEffect + 
        (Math.random() - 0.5) * 0.05 + // Random noise
        (moneyness < 1 ? 0.05 : -0.02) // Put skew
      ) * termStructure;
      
      surfaceData.push({
        strike,
        dte,
        moneyness: ((moneyness - 1) * 100),
        impliedVol: impliedVol,
        atmVol: atmVol,
        skew: skewEffect,
        termStructure: termStructure,
        type: moneyness < 1 ? 'ITM' : moneyness > 1 ? 'OTM' : 'ATM',
        volume: Math.floor(Math.random() * 1000) + 50,
        openInterest: Math.floor(Math.random() * 5000) + 100
      });
    });
  });
  
  return surfaceData;
};

// Calculate volatility term structure
const calculateTermStructure = (surfaceData) => {
  const expiries = [...new Set(surfaceData.map(d => d.dte))].sort((a, b) => a - b);
  
  return expiries.map(dte => {
    const atmOptions = surfaceData.filter(d => 
      d.dte === dte && Math.abs(d.moneyness) < 2.5
    );
    
    const avgIV = atmOptions.length > 0 ? 
      atmOptions.reduce((sum, opt) => sum + opt.impliedVol, 0) / atmOptions.length : 0;
    
    return {
      dte,
      atmIV: avgIV,
      ivRank: Math.random() * 100, // IV Rank vs historical
      ivPercentile: Math.random() * 100 // IV Percentile
    };
  });
};

// Calculate volatility skew
const calculateVolatilitySkew = (surfaceData, selectedExpiry = 30) => {
  const expiryData = surfaceData.filter(d => d.dte === selectedExpiry);
  
  return expiryData
    .sort((a, b) => a.strike - b.strike)
    .map(d => ({
      strike: d.strike,
      moneyness: d.moneyness,
      impliedVol: d.impliedVol * 100,
      type: d.type,
      volume: d.volume
    }));
};

// Surface analysis metrics
const analyzeSurface = (surfaceData, spotPrice) => {
  const atmData = surfaceData.filter(d => Math.abs(d.moneyness) < 2.5);
  const shortTermData = surfaceData.filter(d => d.dte <= 30);
  const longTermData = surfaceData.filter(d => d.dte >= 60);
  
  const avgATMVol = atmData.reduce((sum, d) => sum + d.impliedVol, 0) / atmData.length;
  const avgShortVol = shortTermData.reduce((sum, d) => sum + d.impliedVol, 0) / shortTermData.length;
  const avgLongVol = longTermData.reduce((sum, d) => sum + d.impliedVol, 0) / longTermData.length;
  
  // Calculate put-call skew
  const putsData = surfaceData.filter(d => d.moneyness < -5);
  const callsData = surfaceData.filter(d => d.moneyness > 5);
  const avgPutVol = putsData.reduce((sum, d) => sum + d.impliedVol, 0) / putsData.length;
  const avgCallVol = callsData.reduce((sum, d) => sum + d.impliedVol, 0) / callsData.length;
  
  return {
    avgATMVol: (avgATMVol * 100).toFixed(1),
    termStructure: avgShortVol > avgLongVol ? 'Backwardation' : 'Contango',
    putCallSkew: ((avgPutVol - avgCallVol) * 100).toFixed(1),
    ivRank: Math.floor(Math.random() * 100),
    volatilityRegime: avgATMVol > 0.3 ? 'High Vol' : avgATMVol > 0.2 ? 'Medium Vol' : 'Low Vol',
    trend: Math.random() > 0.5 ? 'Increasing' : 'Decreasing'
  };
};

const VolatilitySurface = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState(0);
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [selectedExpiry, setSelectedExpiry] = useState(30);
  const [viewMode, setViewMode] = useState('surface'); // surface, skew, term
  const [show3D, setShow3D] = useState(false);
  
  // Data states
  const [surfaceData, setSurfaceData] = useState([]);
  const [termStructure, setTermStructure] = useState([]);
  const [volatilitySkew, setVolatilitySkew] = useState([]);
  const [surfaceAnalysis, setSurfaceAnalysis] = useState(null);
  const [currentPrice, setCurrentPrice] = useState(150.25);
  
  // Controls
  const [moneynessBounds, setMoneynessBounds] = useState([-20, 20]);
  const [expiryBounds, setExpiryBounds] = useState([7, 365]);
  
  const symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'SPY', 'QQQ', 'IWM'];
  const expiries = [7, 14, 21, 30, 45, 60, 90, 120, 180, 365];
  
  useEffect(() => {
    loadVolatilityData();
  }, [selectedSymbol, selectedExpiry]);
  
  const loadVolatilityData = () => {
    setLoading(true);
    
    try {
      // Simulate realistic market data
      const price = 150.25 + (Math.random() - 0.5) * 10;
      setCurrentPrice(price);
      
      const surface = generateVolatilitySurface(selectedSymbol, price);
      const term = calculateTermStructure(surface);
      const skew = calculateVolatilitySkew(surface, selectedExpiry);
      const analysis = analyzeSurface(surface, price);
      
      setSurfaceData(surface);
      setTermStructure(term);
      setVolatilitySkew(skew);
      setSurfaceAnalysis(analysis);
      
    } catch (err) {
      setError('Failed to load volatility surface data');
    } finally {
      setLoading(false);
    }
  };
  
  // Filter surface data based on bounds
  const filteredSurfaceData = useMemo(() => {
    return surfaceData.filter(d => 
      d.moneyness >= moneynessBounds[0] && 
      d.moneyness <= moneynessBounds[1] &&
      d.dte >= expiryBounds[0] && 
      d.dte <= expiryBounds[1]
    );
  }, [surfaceData, moneynessBounds, expiryBounds]);
  
  const getVolatilityColor = (vol) => {
    if (vol < 0.15) return '#00C49F'; // Low vol - green
    if (vol < 0.25) return '#FFBB28'; // Medium vol - yellow
    if (vol < 0.35) return '#FF8042'; // High vol - orange
    return '#FF4444'; // Very high vol - red
  };
  
  const getSkewColor = (moneyness) => {
    if (Math.abs(moneyness) < 2.5) return '#8884d8'; // ATM
    if (moneyness < 0) return '#82ca9d'; // ITM/Puts
    return '#ffc658'; // OTM/Calls
  };
  
  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          Volatility Surface Analysis
        </div>
        <div  variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Advanced 3D volatility surface modeling, skew analysis, and term structure visualization
        </div>
        <div  display="flex" gap={1} flexWrap="wrap">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="3D Surface" color="primary" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Volatility Skew" color="success" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Term Structure" color="info" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="IV Rank & Percentile" color="warning" size="small" variant="outlined" />
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
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Expiry (Days)</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={selectedExpiry}
                  label="Expiry (Days)"
                  onChange={(e) => setSelectedExpiry(e.target.value)}
                >
                  {expiries.map(exp => (
                    <option  key={exp} value={exp}>{exp}d</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">View Mode</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={viewMode}
                  label="View Mode"
                  onChange={(e) => setViewMode(e.target.value)}
                >
                  <option  value="surface">3D Surface</option>
                  <option  value="skew">Volatility Skew</option>
                  <option  value="term">Term Structure</option>
                  <option  value="heatmap">IV Heatmap</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                startIcon={loading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} /> : <↻  />}
                onClick={loadVolatilityData}
                disabled={loading}
                fullWidth
              >
                Refresh
              </button>
            </div>
            <div className="grid" item xs={12} sm={4}>
              {surfaceAnalysis && (
                <div  display="flex" gap={2}>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">ATM IV</div>
                    <div  variant="h6" fontWeight="bold">
                      {surfaceAnalysis.avgATMVol}%
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">IV Rank</div>
                    <div  variant="h6" fontWeight="bold" color="warning.main">
                      {surfaceAnalysis.ivRank}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="caption" color="text.secondary">Regime</div>
                    <div  variant="h6" fontWeight="bold">
                      {surfaceAnalysis.volatilityRegime}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="grid" container spacing={3}>
        {/* Main Visualization */}
        <div className="grid" item xs={12} lg={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header 
              title={`Volatility ${viewMode.charAt(0).toUpperCase() + viewMode.slice(1)} - ${selectedSymbol}`}
              subheader={`Current Price: $${currentPrice.toFixed(2)}`}
              action={
                <div  display="flex" gap={1}>
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle" 
                        checked={show3D} 
                        onChange={(e) => setShow3D(e.target.checked)}
                        size="small"
                      />
                    }
                    label="3D View"
                  />
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
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Surface View" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Skew Analysis" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Term Structure" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Data Table" />
              </div>
              
              {loading ? (
                <div  display="flex" justifyContent="center" py={4}>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
                </div>
              ) : (
                <>
                  {activeTab === 0 && (
                    <div>
                      <ResponsiveContainer width="100%" height={500}>
                        <ScatterChart data={filteredSurfaceData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="moneyness" 
                            type="number" 
                            domain={moneynessBounds}
                            label={{ value: 'Moneyness (%)', position: 'insideBottom', offset: -10 }}
                          />
                          <YAxis 
                            dataKey="dte" 
                            type="number" 
                            domain={expiryBounds}
                            label={{ value: 'Days to Expiry', angle: -90, position: 'insideLeft' }}
                          />
                          <ZAxis 
                            dataKey="impliedVol" 
                            range={[20, 200]}
                          />
                          <RechartsTooltip 
                            formatter={(value, name) => {
                              if (name === 'impliedVol') return [`${(value * 100).toFixed(1)}%`, 'IV'];
                              return [value, name];
                            }}
                            labelFormatter={(value) => `Moneyness: ${value}%`}
                          />
                          <Scatter 
                            data={filteredSurfaceData} 
                            fill={(entry) => getVolatilityColor(entry.impliedVol)}
                          />
                        </ScatterChart>
                      </ResponsiveContainer>
                      <div  variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                        Bubble size represents implied volatility level. Color indicates vol regime.
                      </div>
                    </div>
                  )}
                  
                  {activeTab === 1 && (
                    <div>
                      <ResponsiveContainer width="100%" height={400}>
                        <LineChart data={volatilitySkew}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="strike" 
                            label={{ value: 'Strike Price ($)', position: 'insideBottom', offset: -10 }}
                          />
                          <YAxis 
                            label={{ value: 'Implied Volatility (%)', angle: -90, position: 'insideLeft' }}
                          />
                          <RechartsTooltip 
                            formatter={(value) => [`${value.toFixed(1)}%`, 'IV']}
                            labelFormatter={(strike) => `Strike: $${strike}`}
                          />
                          <Line 
                            type="monotone" 
                            dataKey="impliedVol" 
                            stroke="#8884d8" 
                            strokeWidth={3}
                            dot={{ fill: '#8884d8', strokeWidth: 2, r: 4 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                      <div  mt={2}>
                        <div  variant="h6" gutterBottom>Skew Analysis</div>
                        <div className="grid" container spacing={2}>
                          <div className="grid" item xs={4}>
                            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                              <div  variant="h5" color="primary">
                                {surfaceAnalysis?.putCallSkew}%
                              </div>
                              <div  variant="caption">Put-Call Skew</div>
                            </div>
                          </div>
                          <div className="grid" item xs={4}>
                            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                              <div  variant="h5" color="secondary">
                                {selectedExpiry}d
                              </div>
                              <div  variant="caption">Expiry</div>
                            </div>
                          </div>
                          <div className="grid" item xs={4}>
                            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                              <div  variant="h5" color="success.main">
                                {Math.max(...volatilitySkew.map(d => d.impliedVol)).toFixed(1)}%
                              </div>
                              <div  variant="caption">Peak IV</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {activeTab === 2 && (
                    <div>
                      <ResponsiveContainer width="100%" height={400}>
                        <AreaChart data={termStructure}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="dte" 
                            label={{ value: 'Days to Expiry', position: 'insideBottom', offset: -10 }}
                          />
                          <YAxis 
                            label={{ value: 'ATM Implied Volatility', angle: -90, position: 'insideLeft' }}
                            tickFormatter={(value) => `${(value * 100).toFixed(0)}%`}
                          />
                          <RechartsTooltip 
                            formatter={(value) => [`${(value * 100).toFixed(1)}%`, 'ATM IV']}
                            labelFormatter={(dte) => `${dte} days to expiry`}
                          />
                          <Area 
                            type="monotone" 
                            dataKey="atmIV" 
                            stroke="#82ca9d" 
                            fill="#82ca9d"
                            fillOpacity={0.3}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                      <div  mt={2}>
                        <div  variant="h6" gutterBottom>Term Structure Analysis</div>
                        <div className="grid" container spacing={2}>
                          <div className="grid" item xs={6}>
                            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                              <div  variant="h5" color="primary">
                                {surfaceAnalysis?.termStructure}
                              </div>
                              <div  variant="caption">Structure Type</div>
                            </div>
                          </div>
                          <div className="grid" item xs={6}>
                            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                              <div  variant="h5" color="warning.main">
                                {surfaceAnalysis?.trend}
                              </div>
                              <div  variant="caption">IV Trend</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {activeTab === 3 && (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined" sx={{ maxHeight: 500 }}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Strike</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Expiry</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Moneyness</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">IV</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">OI</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Type</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {filteredSurfaceData.slice(0, 50).map((row, index) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index} hover>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>${row.strike.toFixed(2)}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{row.dte}d</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                <div  
                                  variant="body2" 
                                  color={Math.abs(row.moneyness) < 2.5 ? 'primary.main' : 'text.secondary'}
                                >
                                  {row.moneyness.toFixed(1)}%
                                </div>
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                <div  sx={{ color: getVolatilityColor(row.impliedVol) }}>
                                  {(row.impliedVol * 100).toFixed(1)}%
                                </div>
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.volume.toLocaleString()}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{row.openInterest.toLocaleString()}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={row.type} 
                                  color={row.type === 'ATM' ? 'primary' : row.type === 'ITM' ? 'success' : 'warning'}
                                  size="small"
                                  variant="outlined"
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar Analysis */}
        <div className="grid" item xs={12} lg={4}>
          {/* Surface Metrics */}
          {surfaceAnalysis && (
            <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
              <div className="bg-white shadow-md rounded-lg"Header title="Surface Metrics" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">ATM Volatility</div>
                    <div  variant="h6" fontWeight="bold">
                      {surfaceAnalysis.avgATMVol}%
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">IV Rank</div>
                    <div  variant="h6" fontWeight="bold" color="warning.main">
                      {surfaceAnalysis.ivRank}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Put-Call Skew</div>
                    <div  variant="h6" fontWeight="bold">
                      {surfaceAnalysis.putCallSkew}%
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Vol Regime</div>
                    <div  variant="h6" fontWeight="bold">
                      {surfaceAnalysis.volatilityRegime}
                    </div>
                  </div>
                </div>
                <hr className="border-gray-200" sx={{ my: 2 }} />
                <div>
                  <div  variant="caption" color="text.secondary">Term Structure</div>
                  <div  variant="body1" fontWeight="bold">
                    {surfaceAnalysis.termStructure}
                  </div>
                  <div  variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                    {surfaceAnalysis.termStructure === 'Contango' ? 
                      'Front month IV < back month IV' : 
                      'Front month IV > back month IV'}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Controls */}
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Display Controls" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ mb: 3 }}>
                <div  variant="subtitle2" gutterBottom>
                  Moneyness Range (%)
                </div>
                <Slider
                  value={moneynessBounds}
                  onChange={(_, newValue) => setMoneynessBounds(newValue)}
                  valueLabelDisplay="auto"
                  min={-50}
                  max={50}
                  step={5}
                />
              </div>
              <div  sx={{ mb: 3 }}>
                <div  variant="subtitle2" gutterBottom>
                  Days to Expiry Range
                </div>
                <Slider
                  value={expiryBounds}
                  onChange={(_, newValue) => setExpiryBounds(newValue)}
                  valueLabelDisplay="auto"
                  min={1}
                  max={365}
                  step={7}
                />
              </div>
              <div>
                <div  variant="subtitle2" gutterBottom>
                  Analysis Notes
                </div>
                <div  variant="body2" color="text.secondary">
                  • Higher IV for OTM options indicates volatility skew
                  • Term structure shows volatility expectations over time
                  • IV rank compares current levels to historical range
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VolatilitySurface;