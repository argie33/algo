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
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <Box textAlign="center">
            <CircularProgress size={60} />
            <Typography variant="h6" sx={{ mt: 2 }}>
              Loading Sector Analysis...
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Analyzing {timeframe} data from live tables
            </Typography>
          </Box>
        </Box>
      </Container>
    );
  }

  const sortedData = getSortedSectorData();

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <Box>
          <Typography variant="h4" component="h1" fontWeight="bold" gutterBottom>
            Sector Analysis
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Comprehensive sector performance analysis with live momentum data
          </Typography>
        </Box>
        <Box display="flex" gap={2} alignItems="center">
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={timeframe}
              label="Timeframe"
              onChange={(e) => setTimeframe(e.target.value)}
            >
              <MenuItem value="daily">Daily</MenuItem>
              <MenuItem value="weekly">Weekly</MenuItem>
              <MenuItem value="monthly">Monthly</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Sort By</InputLabel>
            <Select
              value={sortBy}
              label="Sort By"
              onChange={(e) => setSortBy(e.target.value)}
            >
              <MenuItem value="monthly_change">Performance</MenuItem>
              <MenuItem value="momentum">Momentum</MenuItem>
              <MenuItem value="volume">Volume</MenuItem>
              <MenuItem value="name">Name</MenuItem>
            </Select>
          </FormControl>
          <FormControlLabel
            control={
              <Switch
                checked={showMomentum}
                onChange={(e) => setShowMomentum(e.target.checked)}
              />
            }
            label="Momentum"
          />
          <IconButton onClick={fetchSectorData} color="primary">
            <RefreshIcon />
          </IconButton>
        </Box>
      </Box>

      {error && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          <Typography variant="body2">
            {String(error)}
          </Typography>
          <Typography variant="caption" display="block" sx={{ mt: 1 }}>
            Showing mock data for development. Deploy the backend to see live data.
          </Typography>
        </Alert>
      )}

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <BusinessIcon color="primary" />
                <Box>
                  <Typography variant="h6">{sortedData.length}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    Sectors Analyzed
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <AssessmentIcon color="success" />
                <Box>
                  <Typography variant="h6">
                    {sortedData.filter(s => parseFloat(s.metrics.performance.monthly_change) > 0).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Positive Sectors
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <SpeedIcon color="info" />
                <Box>
                  <Typography variant="h6">
                    {sortedData.filter(s => parseFloat(s.metrics.momentum?.jt_momentum_12_1 || 0) > 0).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Positive Momentum
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <TimelineIcon color="warning" />
                <Box>
                  <Typography variant="h6">
                    {lastUpdated ? lastUpdated.toLocaleTimeString() : 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Last Updated
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Sector Performance Chart */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Sector Performance ({timeframe})
          </Typography>
          <Box sx={{ height: 400 }}>
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
          </Box>
        </CardContent>
      </Card>

      {/* Sector Details Table */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Detailed Sector Analysis
          </Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Sector</TableCell>
                  <TableCell align="right">Stocks</TableCell>
                  <TableCell align="right">Monthly Return</TableCell>
                  <TableCell align="right">Weekly Return</TableCell>
                  <TableCell align="right">Daily Return</TableCell>
                  {showMomentum && (
                    <>
                      <TableCell align="right">JT Momentum</TableCell>
                      <TableCell align="right">Momentum Signal</TableCell>
                    </>
                  )}
                  <TableCell align="right">Avg RSI</TableCell>
                  <TableCell align="right">Trend</TableCell>
                  <TableCell align="center">Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedData.map((sector) => {
                  const momentumSignal = getMomentumSignal(sector.metrics.momentum?.jt_momentum_12_1 || 0);
                  
                  return (
                    <TableRow 
                      key={sector.sector} 
                      hover
                      sx={{ cursor: 'pointer' }}
                      onClick={() => handleSectorClick(sector.sector)}
                    >
                      <TableCell>
                        <Box>
                          <Typography variant="subtitle2" fontWeight="bold">
                            {sector.sector}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {sector.industry}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        {sector.metrics.priced_stocks}/{sector.metrics.stock_count}
                      </TableCell>
                      <TableCell align="right">
                        <Box display="flex" alignItems="center" justifyContent="flex-end" gap={1}>
                          {getPerformanceIcon(sector.metrics.performance.monthly_change)}
                          <Typography
                            variant="body2"
                            sx={{ color: getChangeColor(sector.metrics.performance.monthly_change) }}
                          >
                            {sector.metrics.performance.monthly_change}%
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography
                          variant="body2"
                          sx={{ color: getChangeColor(sector.metrics.performance.weekly_change) }}
                        >
                          {sector.metrics.performance.weekly_change}%
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography
                          variant="body2"
                          sx={{ color: getChangeColor(sector.metrics.performance.daily_change) }}
                        >
                          {sector.metrics.performance.daily_change}%
                        </Typography>
                      </TableCell>
                      {showMomentum && (
                        <>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {(parseFloat(sector.metrics.momentum?.jt_momentum_12_1 || 0) * 100).toFixed(2)}%
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Chip
                              label={momentumSignal.label}
                              color={momentumSignal.color}
                              size="small"
                            />
                          </TableCell>
                        </>
                      )}
                      <TableCell align="right">
                        <Typography variant="body2">
                          {parseFloat(sector.metrics.technicals?.avg_rsi || 0).toFixed(1)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Box display="flex" justifyContent="flex-end" gap={1}>
                          <Chip
                            label={`${sector.metrics.technicals?.trend_distribution?.bullish || 0}B`}
                            color="success"
                            size="small"
                            variant="outlined"
                          />
                          <Chip
                            label={`${sector.metrics.technicals?.trend_distribution?.bearish || 0}B`}
                            color="error"
                            size="small"
                            variant="outlined"
                          />
                        </Box>
                      </TableCell>
                      <TableCell align="center">
                        <IconButton size="small" color="primary">
                          <VisibilityIcon />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* Sector Details Modal/Drawer could be added here */}
      {selectedSector && sectorDetails && (
        <Card sx={{ mt: 4 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {selectedSector} Sector Details
            </Typography>
            {detailsLoading ? (
              <Box display="flex" justifyContent="center" py={4}>
                <CircularProgress />
              </Box>
            ) : (
              <Box>
                <Typography variant="body2" sx={{ mb: 2 }}>
                  {sectorDetails.summary.stock_count} stocks analyzed across {sectorDetails.summary.industry_count} industries
                </Typography>
                
                {/* Industry breakdown */}
                <Typography variant="subtitle2" gutterBottom>
                  Industry Performance:
                </Typography>
                <Box display="flex" gap={1} flexWrap="wrap" sx={{ mb: 2 }}>
                  {sectorDetails.industries?.map((industry) => (
                    <Chip
                      key={industry.industry}
                      label={`${industry.industry}: ${industry.avg_return.toFixed(1)}%`}
                      color={industry.avg_return > 0 ? 'success' : 'error'}
                      variant="outlined"
                      size="small"
                    />
                  ))}
                </Box>

                {/* Top stocks */}
                <Typography variant="subtitle2" gutterBottom>
                  Top Performers:
                </Typography>
                <Box display="flex" gap={1} flexWrap="wrap">
                  {sectorDetails.stocks?.slice(0, 5).map((stock) => (
                    <Chip
                      key={stock.symbol}
                      label={`${stock.symbol}: ${stock.performance.monthly_change}%`}
                      color="success"
                      size="small"
                    />
                  ))}
                </Box>
              </Box>
            )}
          </CardContent>
        </Card>
      )}
    </Container>
  );
}

export default SectorAnalysis;