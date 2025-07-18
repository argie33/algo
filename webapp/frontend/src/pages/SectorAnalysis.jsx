import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CircularProgress,
  Alert,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Button,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Badge
} from '@mui/material';
import {
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Timeline as TimelineIcon,
  BusinessCenter as BusinessIcon,
  Assessment as AssessmentIcon,
  Refresh as RefreshIcon,
  Info as InfoIcon,
  ExpandMore as ExpandMoreIcon,
  Speed as SpeedIcon,
  Visibility as VisibilityIcon
} from '@mui/icons-material';
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip as RechartsTooltip, 
  ResponsiveContainer, 
  Cell, 
  PieChart, 
  Pie, 
  Legend,
  LineChart,
  Line,
  Area,
  AreaChart
} from 'recharts';
import { getSectorAnalysis, getSectorDetails } from '../services/api';

function SectorAnalysis() {
  const [sectorData, setSectorData] = useState([]);
  const [selectedSector, setSelectedSector] = useState(null);
  const [sectorDetails, setSectorDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [timeframe, setTimeframe] = useState('daily');
  const [sortBy, setSortBy] = useState('monthly_change');
  const [showMomentum, setShowMomentum] = useState(true);

  const fetchSectorData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      console.log('📊 Fetching sector analysis data...');
      const result = await getSectorAnalysis(timeframe);
      
      if (result.success) {
        setSectorData(result.data.sectors || []);
        setLastUpdated(new Date());
        console.log(`✅ Loaded ${result.data.sectors?.length || 0} sectors`);
      } else {
        throw new Error(result.error || 'Failed to fetch sector data');
      }
    } catch (err) {
      console.error('❌ Error fetching sector data:', err);
      setError(err.message);
      
      // Fallback to mock data for development
      const mockData = generateMockSectorData();
      setSectorData(mockData);
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  };

  const fetchSectorDetails = async (sector) => {
    try {
      setDetailsLoading(true);
      
      console.log(`📊 Fetching details for sector: ${sector}`);
      const result = await getSectorDetails(sector);
      
      if (result.success) {
        setSectorDetails(result.data);
        console.log(`✅ Loaded details for ${sector}: ${result.data.stocks?.length || 0} stocks`);
      } else {
        throw new Error(result.error || 'Failed to fetch sector details');
      }
    } catch (err) {
      console.error(`❌ Error fetching ${sector} details:`, err);
      // Generate mock details for development
      setSectorDetails(generateMockSectorDetails(sector));
    } finally {
      setDetailsLoading(false);
    }
  };

  useEffect(() => {
    fetchSectorData();
  }, [timeframe]);

  const handleSectorClick = (sector) => {
    setSelectedSector(sector);
    fetchSectorDetails(sector);
  };

  const getSortedSectorData = () => {
    if (!sectorData.length) return [];
    
    return [...sectorData].sort((a, b) => {
      switch (sortBy) {
        case 'monthly_change':
          return parseFloat(b.metrics.performance.monthly_change) - parseFloat(a.metrics.performance.monthly_change);
        case 'momentum':
          return parseFloat(b.metrics.momentum.jt_momentum_12_1) - parseFloat(a.metrics.momentum.jt_momentum_12_1);
        case 'volume':
          return parseInt(b.metrics.volume.avg_volume) - parseInt(a.metrics.volume.avg_volume);
        case 'name':
          return a.sector.localeCompare(b.sector);
        default:
          return 0;
      }
    });
  };

  const getChangeColor = (value) => {
    const num = parseFloat(value);
    if (num > 0) return 'success.main';
    if (num < 0) return 'error.main';
    return 'text.secondary';
  };

  const getPerformanceIcon = (value) => {
    const num = parseFloat(value);
    if (num > 0) return <TrendingUpIcon color="success" />;
    if (num < 0) return <TrendingDownIcon color="error" />;
    return <TimelineIcon color="action" />;
  };

  const getMomentumSignal = (momentum) => {
    const value = parseFloat(momentum);
    if (value > 0.02) return { label: 'Strong', color: 'success' };
    if (value > 0) return { label: 'Positive', color: 'info' };
    if (value < -0.02) return { label: 'Weak', color: 'error' };
    return { label: 'Neutral', color: 'default' };
  };

  const generateMockSectorData = () => [
    {
      sector: 'Technology',
      industry: 'Software',
      metrics: {
        stock_count: 45,
        priced_stocks: 42,
        performance: { monthly_change: '8.5', weekly_change: '2.1', daily_change: '0.8' },
        momentum: { jt_momentum_12_1: '0.0850', momentum_3m: '0.0420' },
        technicals: { avg_rsi: '65.2', trend_distribution: { bullish: 28, neutral: 10, bearish: 4 } },
        volume: { avg_volume: 2500000 }
      }
    },
    {
      sector: 'Healthcare',
      industry: 'Pharmaceuticals',
      metrics: {
        stock_count: 32,
        priced_stocks: 30,
        performance: { monthly_change: '3.2', weekly_change: '1.5', daily_change: '0.3' },
        momentum: { jt_momentum_12_1: '0.0320', momentum_3m: '0.0180' },
        technicals: { avg_rsi: '58.7', trend_distribution: { bullish: 18, neutral: 8, bearish: 4 } },
        volume: { avg_volume: 1800000 }
      }
    }
  ];

  const generateMockSectorDetails = (sector) => ({
    sector,
    summary: {
      stock_count: 25,
      avg_monthly_return: '5.2',
      industry_count: 3
    },
    industries: [
      { industry: 'Software', count: 15, avg_return: 8.5 },
      { industry: 'Hardware', count: 8, avg_return: 3.2 },
      { industry: 'Semiconductors', count: 2, avg_return: 12.1 }
    ],
    stocks: [
      {
        symbol: 'AAPL',
        name: 'Apple Inc.',
        industry: 'Hardware',
        current_price: '195.50',
        performance: { monthly_change: '12.5' },
        momentum: { jt_momentum_12_1: '0.1250' },
        technicals: { rsi: '68.5', trend: 'bullish' }
      }
    ]
  });

  if (loading) {
    return (
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <div  textAlign="center">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
            <div  variant="h6" sx={{ mt: 2 }}>
              Loading Sector Analysis...
            </div>
            <div  variant="body2" color="text.secondary">
              Analyzing {timeframe} data from live tables
            </div>
          </div>
        </div>
      </div>
    );
  }

  const sortedData = getSortedSectorData();

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <div>
          <div  variant="h4" component="h1" fontWeight="bold" gutterBottom>
            Sector Analysis
          </div>
          <div  variant="body1" color="text.secondary">
            Comprehensive sector performance analysis with live momentum data
          </div>
        </div>
        <div  display="flex" gap={2} alignItems="center">
          <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
            <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
            <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={timeframe}
              label="Timeframe"
              onChange={(e) => setTimeframe(e.target.value)}
            >
              <option  value="daily">Daily</option>
              <option  value="weekly">Weekly</option>
              <option  value="monthly">Monthly</option>
            </select>
          </div>
          <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
            <label className="block text-sm font-medium text-gray-700 mb-1">Sort By</label>
            <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={sortBy}
              label="Sort By"
              onChange={(e) => setSortBy(e.target.value)}
            >
              <option  value="monthly_change">Performance</option>
              <option  value="momentum">Momentum</option>
              <option  value="volume">Volume</option>
              <option  value="name">Name</option>
            </select>
          </div>
          <div className="mb-4"Label
            control={
              <input type="checkbox" className="toggle"
                checked={showMomentum}
                onChange={(e) => setShowMomentum(e.target.checked)}
              />
            }
            label="Momentum"
          />
          <button className="p-2 rounded-full hover:bg-gray-100" onClick={fetchSectorData} color="primary">
            <↻  />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" sx={{ mb: 3 }}>
          <div  variant="body2">
            {String(error)}
          </div>
          <div  variant="caption" display="block" sx={{ mt: 1 }}>
            Showing mock data for development. Deploy the backend to see live data.
          </div>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" gap={2}>
                <BusinessIcon color="primary" />
                <div>
                  <div  variant="h6">{sortedData.length}</div>
                  <div  variant="body2" color="text.secondary">
                    Sectors Analyzed
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" gap={2}>
                <AssessmentIcon color="success" />
                <div>
                  <div  variant="h6">
                    {sortedData.filter(s => parseFloat(s.metrics.performance.monthly_change) > 0).length}
                  </div>
                  <div  variant="body2" color="text.secondary">
                    Positive Sectors
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" gap={2}>
                <SpeedIcon color="info" />
                <div>
                  <div  variant="h6">
                    {sortedData.filter(s => parseFloat(s.metrics.momentum?.jt_momentum_12_1 || 0) > 0).length}
                  </div>
                  <div  variant="body2" color="text.secondary">
                    Positive Momentum
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" gap={2}>
                <TimelineIcon color="warning" />
                <div>
                  <div  variant="h6">
                    {lastUpdated ? lastUpdated.toLocaleTimeString() : 'N/A'}
                  </div>
                  <div  variant="body2" color="text.secondary">
                    Last Updated
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sector Performance Chart */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 4 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Sector Performance ({timeframe})
          </div>
          <div  sx={{ height: 400 }}>
            <ResponsiveContainer>
              <BarChart data={sortedData.slice(0, 15)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="sector" 
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis />
                <RechartsTooltip 
                  formatter={(value, name) => [`${value}%`, 'Monthly Return']}
                  labelFormatter={(label) => `Sector: ${label}`}
                />
                <Bar dataKey="metrics.performance.monthly_change" name="Monthly Return">
                  {sortedData.slice(0, 15).map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`} 
                      fill={parseFloat(entry.metrics.performance.monthly_change) >= 0 ? '#4caf50' : '#f44336'} 
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Sector Details Table */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Detailed Sector Analysis
          </div>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sector</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Stocks</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Monthly Return</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Weekly Return</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Daily Return</td>
                  {showMomentum && (
                    <>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">JT Momentum</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Momentum Signal</td>
                    </>
                  )}
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Avg RSI</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Trend</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Action</td>
                </tr>
              </thead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                {sortedData.map((sector) => {
                  const momentumSignal = getMomentumSignal(sector.metrics.momentum?.jt_momentum_12_1 || 0);
                  
                  return (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow 
                      key={sector.sector} 
                      hover
                      sx={{ cursor: 'pointer' }}
                      onClick={() => handleSectorClick(sector.sector)}
                    >
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div>
                          <div  variant="subtitle2" fontWeight="bold">
                            {sector.sector}
                          </div>
                          <div  variant="caption" color="text.secondary">
                            {sector.industry}
                          </div>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        {sector.metrics.priced_stocks}/{sector.metrics.stock_count}
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  display="flex" alignItems="center" justifyContent="flex-end" gap={1}>
                          {getPerformanceIcon(sector.metrics.performance.monthly_change)}
                          <div 
                            variant="body2"
                            sx={{ color: getChangeColor(sector.metrics.performance.monthly_change) }}
                          >
                            {sector.metrics.performance.monthly_change}%
                          </div>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div 
                          variant="body2"
                          sx={{ color: getChangeColor(sector.metrics.performance.weekly_change) }}
                        >
                          {sector.metrics.performance.weekly_change}%
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div 
                          variant="body2"
                          sx={{ color: getChangeColor(sector.metrics.performance.daily_change) }}
                        >
                          {sector.metrics.performance.daily_change}%
                        </div>
                      </td>
                      {showMomentum && (
                        <>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2">
                              {(parseFloat(sector.metrics.momentum?.jt_momentum_12_1 || 0) * 100).toFixed(2)}%
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                              label={momentumSignal.label}
                              color={momentumSignal.color}
                              size="small"
                            />
                          </td>
                        </>
                      )}
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  variant="body2">
                          {parseFloat(sector.metrics.technicals?.avg_rsi || 0).toFixed(1)}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  display="flex" justifyContent="flex-end" gap={1}>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            label={`${sector.metrics.technicals?.trend_distribution?.bullish || 0}B`}
                            color="success"
                            size="small"
                            variant="outlined"
                          />
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            label={`${sector.metrics.technicals?.trend_distribution?.bearish || 0}B`}
                            color="error"
                            size="small"
                            variant="outlined"
                          />
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                        <button className="p-2 rounded-full hover:bg-gray-100" size="small" color="primary">
                          <👁  />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Sector Details Modal/Drawer could be added here */}
      {selectedSector && sectorDetails && (
        <div className="bg-white shadow-md rounded-lg" sx={{ mt: 4 }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              {selectedSector} Sector Details
            </div>
            {detailsLoading ? (
              <div  display="flex" justifyContent="center" py={4}>
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
              </div>
            ) : (
              <div>
                <div  variant="body2" sx={{ mb: 2 }}>
                  {sectorDetails.summary.stock_count} stocks analyzed across {sectorDetails.summary.industry_count} industries
                </div>
                
                {/* Industry breakdown */}
                <div  variant="subtitle2" gutterBottom>
                  Industry Performance:
                </div>
                <div  display="flex" gap={1} flexWrap="wrap" sx={{ mb: 2 }}>
                  {sectorDetails.industries?.map((industry) => (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                      key={industry.industry}
                      label={`${industry.industry}: ${industry.avg_return.toFixed(1)}%`}
                      color={industry.avg_return > 0 ? 'success' : 'error'}
                      variant="outlined"
                      size="small"
                    />
                  ))}
                </div>

                {/* Top stocks */}
                <div  variant="subtitle2" gutterBottom>
                  Top Performers:
                </div>
                <div  display="flex" gap={1} flexWrap="wrap">
                  {sectorDetails.stocks?.slice(0, 5).map((stock) => (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                      key={stock.symbol}
                      label={`${stock.symbol}: ${stock.performance.monthly_change}%`}
                      color="success"
                      size="small"
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default SectorAnalysis;