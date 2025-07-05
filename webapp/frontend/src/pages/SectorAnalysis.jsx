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
  LinearProgress,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel
} from '@mui/material';
import {
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Timeline as TimelineIcon,
  BusinessCenter as BusinessIcon,
  Assessment as AssessmentIcon,
  Refresh as RefreshIcon,
  Info as InfoIcon
} from '@mui/icons-material';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts';
import { getMarketSectorPerformance } from '../services/api';

function SectorAnalysis() {
  const [sectorData, setSectorData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [sortBy, setSortBy] = useState('performance');
  const [showRelative, setShowRelative] = useState(false);

  const fetchSectorData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await getMarketSectorPerformance();
      
      if (response.error) {
        throw new Error(response.error);
      }
      
      if (response.data && Array.isArray(response.data)) {
        // Process and enhance the sector data
        const processedData = response.data.map(sector => ({
          ...sector,
          performance: sector.avg_change || 0,
          volume: sector.total_volume || 0,
          marketCap: sector.avg_market_cap || 0,
          stockCount: sector.stock_count || 0
        }));
        
        setSectorData(processedData);
        setLastUpdated(new Date());
      } else {
        throw new Error('Invalid data format received');
      }
    } catch (err) {
      console.error('Error fetching sector data:', err);
      setError(err.message || 'Failed to fetch sector data');
      
      // Fallback data for demonstration
      const fallbackData = [
        { sector: 'Technology', performance: 2.5, volume: 5000000000, marketCap: 50000000000, stockCount: 150 },
        { sector: 'Healthcare', performance: 1.8, volume: 3000000000, marketCap: 40000000000, stockCount: 120 },
        { sector: 'Financial Services', performance: 0.9, volume: 2500000000, marketCap: 35000000000, stockCount: 100 },
        { sector: 'Consumer Discretionary', performance: 1.2, volume: 2000000000, marketCap: 30000000000, stockCount: 80 },
        { sector: 'Industrials', performance: 0.7, volume: 1800000000, marketCap: 25000000000, stockCount: 90 },
        { sector: 'Consumer Staples', performance: 0.4, volume: 1200000000, marketCap: 35000000000, stockCount: 60 },
        { sector: 'Energy', performance: -0.5, volume: 1500000000, marketCap: 20000000000, stockCount: 40 },
        { sector: 'Utilities', performance: 0.1, volume: 800000000, marketCap: 25000000000, stockCount: 30 }
      ];
      setSectorData(fallbackData);
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSectorData();
  }, []);

  const formatNumber = (num, type = 'default') => {
    if (!num) return 'N/A';
    
    switch (type) {
      case 'currency':
        return `$${(num / 1000000000).toFixed(1)}B`;
      case 'volume':
        return `${(num / 1000000).toFixed(0)}M`;
      case 'percentage':
        return `${num.toFixed(2)}%`;
      default:
        return num.toLocaleString();
    }
  };

  const getPerformanceColor = (performance) => {
    if (performance > 1.5) return '#4caf50';
    if (performance > 0.5) return '#8bc34a';
    if (performance > -0.5) return '#ff9800';
    if (performance > -1.5) return '#f44336';
    return '#d32f2f';
  };

  const getPerformanceIcon = (performance) => {
    return performance >= 0 ? <TrendingUpIcon /> : <TrendingDownIcon />;
  };

  const getTrendLabel = (performance) => {
    if (performance > 2) return 'Strong';
    if (performance > 1) return 'Moderate';
    if (performance > 0) return 'Weak';
    if (performance > -1) return 'Declining';
    return 'Weak';
  };

  const sortedSectorData = [...sectorData].sort((a, b) => {
    switch (sortBy) {
      case 'performance':
        return b.performance - a.performance;
      case 'volume':
        return b.volume - a.volume;
      case 'marketCap':
        return b.marketCap - a.marketCap;
      case 'stockCount':
        return b.stockCount - a.stockCount;
      case 'alphabetical':
        return a.sector.localeCompare(b.sector);
      default:
        return b.performance - a.performance;
    }
  });

  const chartData = sortedSectorData.map(sector => ({
    name: sector.sector.length > 15 ? sector.sector.substring(0, 15) + '...' : sector.sector,
    fullName: sector.sector,
    performance: sector.performance,
    volume: sector.volume / 1000000000,
    marketCap: sector.marketCap / 1000000000
  }));

  const pieData = sortedSectorData.map(sector => ({
    name: sector.sector,
    value: Math.abs(sector.performance),
    performance: sector.performance
  }));

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D', '#FFC658', '#8DD1E1'];

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box mb={4}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Box display="flex" alignItems="center" gap={2}>
            <BusinessIcon sx={{ fontSize: 40, color: 'primary.main' }} />
            <Box>
              <Typography variant="h4" component="h1" fontWeight="bold">
                Sector Analysis
              </Typography>
              <Typography variant="subtitle1" color="text.secondary">
                Comprehensive sector performance analysis and rotation insights
              </Typography>
            </Box>
          </Box>
          <Box display="flex" alignItems="center" gap={2}>
            <Tooltip title="Refresh Data">
              <IconButton onClick={fetchSectorData} disabled={loading}>
                <RefreshIcon />
              </IconButton>
            </Tooltip>
            {lastUpdated && (
              <Typography variant="body2" color="text.secondary">
                Last updated: {lastUpdated.toLocaleTimeString()}
              </Typography>
            )}
          </Box>
        </Box>

        {error && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            {error} - Showing sample data for demonstration
          </Alert>
        )}
      </Box>

      {/* Summary Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={2}>
                <TrendingUpIcon color="success" />
                <Box>
                  <Typography variant="h6">
                    {sortedSectorData.filter(s => s.performance > 0).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Advancing Sectors
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
                <TrendingDownIcon color="error" />
                <Box>
                  <Typography variant="h6">
                    {sortedSectorData.filter(s => s.performance < 0).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Declining Sectors
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
                <AssessmentIcon color="primary" />
                <Box>
                  <Typography variant="h6">
                    {formatNumber(sortedSectorData.reduce((sum, s) => sum + s.performance, 0) / sortedSectorData.length, 'percentage')}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Average Performance
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
                <TimelineIcon color="info" />
                <Box>
                  <Typography variant="h6">
                    {sortedSectorData[0]?.sector || 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Top Performer
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Charts Section */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} lg={8}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h6">Sector Performance</Typography>
                <FormControlLabel
                  control={
                    <Switch
                      checked={showRelative}
                      onChange={(e) => setShowRelative(e.target.checked)}
                    />
                  }
                  label="Relative View"
                />
              </Box>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="name" 
                    angle={-45}
                    textAnchor="end"
                    height={100}
                    interval={0}
                  />
                  <YAxis label={{ value: 'Performance (%)', angle: -90, position: 'insideLeft' }} />
                  <RechartsTooltip 
                    formatter={(value, name) => [`${value.toFixed(2)}%`, 'Performance']}
                    labelFormatter={(label) => {
                      const item = chartData.find(d => d.name === label);
                      return item ? item.fullName : label;
                    }}
                  />
                  <Bar dataKey="performance" name="Performance">
                    {chartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={getPerformanceColor(entry.performance)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" mb={3}>Performance Distribution</Typography>
              <ResponsiveContainer width="100%" height={400}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    outerRadius={120}
                    fill="#8884d8"
                    dataKey="value"
                    label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip formatter={(value) => [`${value.toFixed(2)}%`, 'Performance']} />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Detailed Table */}
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
            <Typography variant="h6">Detailed Sector Analysis</Typography>
            <Box display="flex" gap={1}>
              {['performance', 'volume', 'marketCap', 'stockCount', 'alphabetical'].map((sort) => (
                <Chip
                  key={sort}
                  label={sort.charAt(0).toUpperCase() + sort.slice(1)}
                  variant={sortBy === sort ? 'filled' : 'outlined'}
                  onClick={() => setSortBy(sort)}
                  size="small"
                />
              ))}
            </Box>
          </Box>
          
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell><strong>Sector</strong></TableCell>
                  <TableCell align="right"><strong>Performance</strong></TableCell>
                  <TableCell align="right"><strong>Trend</strong></TableCell>
                  <TableCell align="right"><strong>Volume</strong></TableCell>
                  <TableCell align="right"><strong>Avg Market Cap</strong></TableCell>
                  <TableCell align="right"><strong>Stock Count</strong></TableCell>
                  <TableCell align="center"><strong>Momentum</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedSectorData.map((sector, index) => (
                  <TableRow key={sector.sector} hover>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        {getPerformanceIcon(sector.performance)}
                        <Typography variant="body2" fontWeight="medium">
                          {sector.sector}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Typography 
                        variant="body2" 
                        color={sector.performance >= 0 ? 'success.main' : 'error.main'}
                        fontWeight="bold"
                      >
                        {formatNumber(sector.performance, 'percentage')}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={getTrendLabel(sector.performance)}
                        size="small"
                        color={sector.performance >= 0 ? 'success' : 'error'}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {formatNumber(sector.volume, 'volume')}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {formatNumber(sector.marketCap, 'currency')}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {sector.stockCount}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Box width="100%" display="flex" alignItems="center" gap={1}>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(Math.abs(sector.performance) * 20, 100)}
                          sx={{ 
                            flexGrow: 1, 
                            height: 8, 
                            borderRadius: 4,
                            '& .MuiLinearProgress-bar': {
                              backgroundColor: getPerformanceColor(sector.performance)
                            }
                          }}
                        />
                        <Tooltip title={`${formatNumber(sector.performance, 'percentage')} performance`}>
                          <InfoIcon fontSize="small" color="action" />
                        </Tooltip>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* Footer Note */}
      <Box mt={4}>
        <Typography variant="body2" color="text.secondary" align="center">
          Sector analysis based on current market performance, volume, and market capitalization data.
          Performance metrics are calculated as average percentage change for stocks within each sector.
        </Typography>
      </Box>
    </Container>
  );
}

export default SectorAnalysis;