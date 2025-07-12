import React, { useState, useEffect } from 'react';
import { getApiConfig, api } from '../services/api';
import {
  Box,
  Container,
  Typography,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  TextField,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  Tabs,
  Tab,
  CircularProgress,
  Divider,
  Badge,
  Tooltip,
  FormControl,
  InputLabel,
  Select,
  Stack,
  LinearProgress
} from '@mui/material';
import {
  History as HistoryIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Download as DownloadIcon,
  FilterList as FilterIcon,
  Analytics as AnalyticsIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  Assessment as AssessmentIcon,
  AccountBalance as AccountBalanceIcon,
  Timeline as TimelineIcon,
  PieChart as PieChartIcon,
  ShowChart as ShowChartIcon,
  Warning as WarningIcon,
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  Sync as SyncIcon,
  TrendingFlat as TrendingFlatIcon,
  Psychology as PsychologyIcon,
  School as SchoolIcon,
  LightbulbOutlined as LightbulbIcon,
  CompareArrows as CompareArrowsIcon,
  Speed as SpeedIcon,
  Schedule as ScheduleIcon,
  Build as BuildIcon
} from '@mui/icons-material';
import { DatePicker as MuiDatePicker } from '@mui/x-date-pickers/DatePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDateFns } from '@mui/x-date-pickers/AdapterDateFns';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as ChartTooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar } from 'recharts';

const TradeHistory = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [trades, setTrades] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [importStatus, setImportStatus] = useState(null);
  const [filters, setFilters] = useState({
    symbol: '',
    startDate: null,
    endDate: null,
    tradeType: 'all',
    sortBy: 'date',  // Changed from 'execution_time' to more standard 'date'
    sortOrder: 'desc'
  });
  const [pagination, setPagination] = useState({
    page: 0,
    limit: 50,
    total: 0,
    hasMore: false
  });
  const [importDialog, setImportDialog] = useState(false);
  const [importing, setImporting] = useState(false);
  const [alertMessage, setAlertMessage] = useState(null);
  const [timeframe, setTimeframe] = useState('3M');

  useEffect(() => {
    fetchImportStatus();
    fetchTradeHistory();
    fetchAnalytics();
  }, [filters, pagination.page, timeframe]);

  const fetchImportStatus = async () => {
    try {
      const response = await api.get('/api/trades/import/status');
      if (response.data?.success) {
        setImportStatus(response.data);
      }
    } catch (error) {
      console.error('Error fetching import status:', error);
    }
  };

  const fetchTradeHistory = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        ...filters,
        limit: pagination.limit,
        offset: pagination.page * pagination.limit
      });
      
      Object.keys(params).forEach(key => {
        if (!params.get(key) || params.get(key) === 'null') {
          params.delete(key);
        }
      });

      const response = await api.get(`/api/trades/history?${params}`);
      
      if (response.data?.success) {
        setTrades(response.data.data.trades);
        setPagination(prev => ({
          ...prev,
          total: response.data.data.pagination.total,
          hasMore: response.data.data.pagination.hasMore
        }));
      }
    } catch (error) {
      console.error('Error fetching trade history:', error);
      setAlertMessage({ severity: 'error', message: 'Failed to fetch trade history' });
    } finally {
      setLoading(false);
    }
  };

  const fetchAnalytics = async () => {
    try {
      const response = await api.get(`/api/trades/analytics/overview?timeframe=${timeframe}`);
      if (response.data?.success) {
        setAnalytics(response.data.data);
      }
    } catch (error) {
      console.error('Error fetching analytics:', error);
    }
  };

  const handleImportTrades = async () => {
    setImporting(true);
    try {
      const response = await api.post('/api/trades/import/alpaca', {
        startDate: filters.startDate,
        endDate: filters.endDate,
        forceRefresh: true
      });
      
      if (response.data?.success) {
        setAlertMessage({ severity: 'success', message: 'Trades imported successfully!' });
        fetchTradeHistory();
        fetchAnalytics();
        fetchImportStatus();
        setImportDialog(false);
      } else {
        setAlertMessage({ severity: 'error', message: response.data?.error || 'Import failed' });
      }
    } catch (error) {
      console.error('Error importing trades:', error);
      setAlertMessage({ severity: 'error', message: 'Failed to import trades' });
    } finally {
      setImporting(false);
    }
  };

  const handleExport = async (format = 'csv') => {
    try {
      const params = new URLSearchParams({
        format,
        startDate: filters.startDate,
        endDate: filters.endDate
      });
      
      const response = await api.get(`/api/trades/export?${params}`, {
        responseType: format === 'csv' ? 'blob' : 'json'
      });
      
      if (format === 'csv') {
        const blob = response.data;
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `trade_history_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
      } else {
        console.log('Export data:', response.data);
      }
    } catch (error) {
      console.error('Error exporting data:', error);
      setAlertMessage({ severity: 'error', message: 'Failed to export data' });
    }
  };

  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(value);
  };

  const formatPercent = (value) => {
    if (value === null || value === undefined) return '-';
    return `${parseFloat(value).toFixed(2)}%`;
  };

  const getTradeTypeColor = (side) => {
    return side === 'BUY' ? 'success' : 'error';
  };

  const getPnLColor = (pnl) => {
    if (pnl > 0) return 'success';
    if (pnl < 0) return 'error';
    return 'default';
  };

  const AnalyticsOverview = () => (
    <Grid container spacing={3}>
      <Grid item xs={12} md={3}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center">
              <AssessmentIcon color="primary" sx={{ mr: 1 }} />
              <Typography variant="h6">Total Trades</Typography>
            </Box>
            <Typography variant="h4" color="primary">
              {analytics?.overview?.totalTrades || 0}
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={3}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center">
              <TrendingUpIcon color="success" sx={{ mr: 1 }} />
              <Typography variant="h6">Win Rate</Typography>
            </Box>
            <Typography variant="h4" color="success.main">
              {analytics?.overview?.winRate || 0}%
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={3}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center">
              <AccountBalanceIcon color="info" sx={{ mr: 1 }} />
              <Typography variant="h6">Total P&L</Typography>
            </Box>
            <Typography variant="h4" color={getPnLColor(analytics?.overview?.totalPnl)}>
              {formatCurrency(analytics?.overview?.totalPnl)}
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={12} md={3}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center">
              <TimelineIcon color="warning" sx={{ mr: 1 }} />
              <Typography variant="h6">Avg ROI</Typography>
            </Box>
            <Typography variant="h4" color={getPnLColor(analytics?.overview?.avgRoi)}>
              {formatPercent(analytics?.overview?.avgRoi)}
            </Typography>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const TradeTable = () => (
    <Card>
      <CardHeader 
        title="Trade History"
        action={
          <Box display="flex" gap={1}>
            <Button 
              variant="outlined" 
              startIcon={<FilterIcon />}
              onClick={() => setImportDialog(true)}
            >
              Filters
            </Button>
            <Button 
              variant="outlined" 
              startIcon={<DownloadIcon />}
              onClick={() => handleExport('csv')}
            >
              Export
            </Button>
            <Button 
              variant="contained" 
              startIcon={<SyncIcon />}
              onClick={() => setImportDialog(true)}
            >
              Import
            </Button>
          </Box>
        }
      />
      <CardContent>
        {loading ? (
          <Box display="flex" justifyContent="center" p={3}>
            <CircularProgress />
          </Box>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Date</TableCell>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell align="right">Quantity</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Total P&L</TableCell>
                  <TableCell align="right">ROI</TableCell>
                  <TableCell>Pattern</TableCell>
                  <TableCell>Sector</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {trades.map((trade, index) => (
                  <TableRow key={index}>
                    <TableCell>
                      {new Date(trade.execution_time).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {trade.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={trade.side} 
                        color={getTradeTypeColor(trade.side)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">
                      {trade.quantity}
                    </TableCell>
                    <TableCell align="right">
                      {formatCurrency(trade.price)}
                    </TableCell>
                    <TableCell align="right">
                      <Typography color={getPnLColor(trade.net_pnl)}>
                        {formatCurrency(trade.net_pnl)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography color={getPnLColor(trade.return_percentage)}>
                        {formatPercent(trade.return_percentage)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {trade.trade_pattern_type && (
                        <Chip 
                          label={trade.trade_pattern_type} 
                          variant="outlined" 
                          size="small"
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      {trade.sector && (
                        <Chip 
                          label={trade.sector} 
                          color="info"
                          variant="outlined" 
                          size="small"
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
        
        {pagination.hasMore && (
          <Box display="flex" justifyContent="center" mt={2}>
            <Button 
              variant="outlined" 
              onClick={() => setPagination(prev => ({ ...prev, page: prev.page + 1 }))}
            >
              Load More
            </Button>
          </Box>
        )}
      </CardContent>
    </Card>
  );

  // Advanced Analytics Component
  const AdvancedAnalytics = () => {
    // Calculate analytics from trade data
    const calculateAdvancedMetrics = () => {
      if (!trades || trades.length === 0) {
        return {
          patternAnalysis: {},
          riskAttribution: {},
          performanceBenchmark: {},
          timingAnalysis: {},
          learningInsights: []
        };
      }

      const winningTrades = trades.filter(trade => trade.net_pnl > 0);
      const losingTrades = trades.filter(trade => trade.net_pnl < 0);
      
      // Pattern Recognition Analysis
      const patternFrequency = trades.reduce((acc, trade) => {
        const pattern = trade.trade_pattern_type || 'Unknown';
        acc[pattern] = (acc[pattern] || 0) + 1;
        return acc;
      }, {});

      const patternPerformance = Object.keys(patternFrequency).map(pattern => {
        const patternTrades = trades.filter(t => (t.trade_pattern_type || 'Unknown') === pattern);
        const avgReturn = patternTrades.reduce((sum, t) => sum + (t.return_percentage || 0), 0) / patternTrades.length;
        const winRate = patternTrades.filter(t => t.net_pnl > 0).length / patternTrades.length * 100;
        
        return {
          pattern,
          count: patternFrequency[pattern],
          avgReturn: avgReturn || 0,
          winRate: winRate || 0,
          totalPnL: patternTrades.reduce((sum, t) => sum + (t.net_pnl || 0), 0)
        };
      });

      // Sector Analysis
      const sectorPerformance = trades.reduce((acc, trade) => {
        const sector = trade.sector || 'Unknown';
        if (!acc[sector]) {
          acc[sector] = { trades: [], pnl: 0, returns: [] };
        }
        acc[sector].trades.push(trade);
        acc[sector].pnl += trade.net_pnl || 0;
        acc[sector].returns.push(trade.return_percentage || 0);
        return acc;
      }, {});

      const sectorAnalysis = Object.keys(sectorPerformance).map(sector => {
        const data = sectorPerformance[sector];
        const avgReturn = data.returns.reduce((sum, r) => sum + r, 0) / data.returns.length;
        const winRate = data.trades.filter(t => t.net_pnl > 0).length / data.trades.length * 100;
        
        return {
          sector,
          count: data.trades.length,
          totalPnL: data.pnl,
          avgReturn: avgReturn || 0,
          winRate: winRate || 0
        };
      });

      // Risk Attribution
      const avgWinAmount = winningTrades.length > 0 ? 
        winningTrades.reduce((sum, t) => sum + t.net_pnl, 0) / winningTrades.length : 0;
      const avgLossAmount = losingTrades.length > 0 ? 
        Math.abs(losingTrades.reduce((sum, t) => sum + t.net_pnl, 0) / losingTrades.length) : 0;
      
      const profitFactor = avgLossAmount > 0 ? avgWinAmount / avgLossAmount : 0;
      const expectancy = trades.length > 0 ? 
        trades.reduce((sum, t) => sum + (t.net_pnl || 0), 0) / trades.length : 0;

      // Timing Analysis
      const hourlyPnL = trades.reduce((acc, trade) => {
        const hour = new Date(trade.execution_time).getHours();
        acc[hour] = (acc[hour] || 0) + (trade.net_pnl || 0);
        return acc;
      }, {});

      const dailyPnL = trades.reduce((acc, trade) => {
        const day = new Date(trade.execution_time).getDay();
        const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        const dayName = dayNames[day];
        acc[dayName] = (acc[dayName] || 0) + (trade.net_pnl || 0);
        return acc;
      }, {});

      // Learning Insights
      const insights = [];
      
      // Best performing pattern
      const bestPattern = patternPerformance.reduce((best, current) => 
        current.avgReturn > (best?.avgReturn || -Infinity) ? current : best, null);
      if (bestPattern && bestPattern.avgReturn > 0) {
        insights.push({
          type: 'success',
          title: 'Best Performing Pattern',
          message: `${bestPattern.pattern} shows ${bestPattern.avgReturn.toFixed(2)}% avg return with ${bestPattern.winRate.toFixed(0)}% win rate`,
          action: `Focus on identifying more ${bestPattern.pattern} setups`
        });
      }

      // Worst performing pattern
      const worstPattern = patternPerformance.reduce((worst, current) => 
        current.avgReturn < (worst?.avgReturn || Infinity) ? current : worst, null);
      if (worstPattern && worstPattern.avgReturn < 0) {
        insights.push({
          type: 'warning',
          title: 'Underperforming Pattern',
          message: `${worstPattern.pattern} shows ${worstPattern.avgReturn.toFixed(2)}% avg return`,
          action: `Review or avoid ${worstPattern.pattern} setups until improved`
        });
      }

      // Risk management insights
      if (profitFactor < 1.5) {
        insights.push({
          type: 'warning',
          title: 'Risk Management Alert',
          message: `Profit factor of ${profitFactor.toFixed(2)} suggests poor risk/reward ratio`,
          action: 'Consider tighter stop losses or higher profit targets'
        });
      }

      // Best trading times
      const bestHour = Object.keys(hourlyPnL).reduce((best, hour) => 
        hourlyPnL[hour] > (hourlyPnL[best] || -Infinity) ? hour : best, '0');
      if (hourlyPnL[bestHour] > 0) {
        insights.push({
          type: 'info',
          title: 'Optimal Trading Time',
          message: `Best performance at ${bestHour}:00 with $${hourlyPnL[bestHour].toFixed(2)} total P&L`,
          action: 'Consider focusing trading activity during this time'
        });
      }

      return {
        patternAnalysis: {
          patterns: patternPerformance,
          frequency: patternFrequency
        },
        riskAttribution: {
          profitFactor,
          expectancy,
          avgWin: avgWinAmount,
          avgLoss: avgLossAmount,
          winRate: trades.length > 0 ? winningTrades.length / trades.length * 100 : 0
        },
        performanceBenchmark: {
          sectors: sectorAnalysis,
          totalTrades: trades.length,
          totalPnL: trades.reduce((sum, t) => sum + (t.net_pnl || 0), 0)
        },
        timingAnalysis: {
          hourly: hourlyPnL,
          daily: dailyPnL
        },
        learningInsights: insights
      };
    };

    const metrics = calculateAdvancedMetrics();
    const colors = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#00ff00', '#ff00ff', '#00ffff'];

    return (
      <Box>
        {/* Pattern Recognition Section */}
        <Card sx={{ mb: 3 }}>
          <CardHeader
            title="Pattern Recognition Analysis"
            avatar={<PsychologyIcon color="primary" />}
            subheader="Identify which trading patterns work best for you"
          />
          <CardContent>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Pattern Performance</Typography>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={metrics.patternAnalysis.patterns}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="pattern" />
                    <YAxis />
                    <ChartTooltip formatter={(value, name) => [
                      name === 'avgReturn' ? `${value.toFixed(2)}%` : value.toFixed(2),
                      name === 'avgReturn' ? 'Avg Return' : 'Win Rate %'
                    ]} />
                    <Bar dataKey="avgReturn" fill="#8884d8" name="avgReturn" />
                    <Bar dataKey="winRate" fill="#82ca9d" name="winRate" />
                  </BarChart>
                </ResponsiveContainer>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Pattern Frequency</Typography>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={Object.keys(metrics.patternAnalysis.frequency).map((key, index) => ({
                        name: key,
                        value: metrics.patternAnalysis.frequency[key],
                        fill: colors[index % colors.length]
                      }))}
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      dataKey="value"
                      label={({ name, value }) => `${name}: ${value}`}
                    />
                    <ChartTooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Risk Attribution Section */}
        <Card sx={{ mb: 3 }}>
          <CardHeader
            title="Risk Attribution Analysis"
            avatar={<WarningIcon color="warning" />}
            subheader="Understand your risk/reward profile and improve risk management"
          />
          <CardContent>
            <Grid container spacing={3}>
              <Grid item xs={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography color="text.secondary" gutterBottom>Profit Factor</Typography>
                    <Typography variant="h4" color={metrics.riskAttribution.profitFactor >= 1.5 ? 'success.main' : 'error.main'}>
                      {metrics.riskAttribution.profitFactor.toFixed(2)}
                    </Typography>
                    <Typography variant="body2">
                      {metrics.riskAttribution.profitFactor >= 1.5 ? 'Good' : 'Needs Improvement'}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography color="text.secondary" gutterBottom>Expectancy</Typography>
                    <Typography variant="h4" color={metrics.riskAttribution.expectancy >= 0 ? 'success.main' : 'error.main'}>
                      ${metrics.riskAttribution.expectancy.toFixed(2)}
                    </Typography>
                    <Typography variant="body2">Per Trade</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography color="text.secondary" gutterBottom>Avg Win</Typography>
                    <Typography variant="h4" color="success.main">
                      ${metrics.riskAttribution.avgWin.toFixed(2)}
                    </Typography>
                    <Typography variant="body2">Average</Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6} md={3}>
                <Card variant="outlined">
                  <CardContent>
                    <Typography color="text.secondary" gutterBottom>Avg Loss</Typography>
                    <Typography variant="h4" color="error.main">
                      ${metrics.riskAttribution.avgLoss.toFixed(2)}
                    </Typography>
                    <Typography variant="body2">Average</Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Performance Benchmarking Section */}
        <Card sx={{ mb: 3 }}>
          <CardHeader
            title="Performance Benchmarking"
            avatar={<CompareArrowsIcon color="info" />}
            subheader="Compare performance across sectors and identify strengths"
          />
          <CardContent>
            <Typography variant="h6" gutterBottom>Sector Performance</Typography>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={metrics.performanceBenchmark.sectors}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="sector" />
                <YAxis />
                <ChartTooltip formatter={(value, name) => [
                  name === 'totalPnL' ? `$${value.toFixed(2)}` : `${value.toFixed(1)}%`,
                  name === 'totalPnL' ? 'Total P&L' : name === 'avgReturn' ? 'Avg Return' : 'Win Rate'
                ]} />
                <Bar dataKey="totalPnL" fill="#8884d8" name="totalPnL" />
                <Bar dataKey="avgReturn" fill="#82ca9d" name="avgReturn" />
                <Bar dataKey="winRate" fill="#ffc658" name="winRate" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Timing Analysis Section */}
        <Card sx={{ mb: 3 }}>
          <CardHeader
            title="Trade Timing Analysis"
            avatar={<ScheduleIcon color="primary" />}
            subheader="Discover optimal trading times and patterns"
          />
          <CardContent>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Daily Performance</Typography>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={Object.keys(metrics.timingAnalysis.daily).map(day => ({
                    day,
                    pnl: metrics.timingAnalysis.daily[day]
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="day" />
                    <YAxis />
                    <ChartTooltip formatter={(value) => [`$${value.toFixed(2)}`, 'P&L']} />
                    <Bar dataKey="pnl" fill="#8884d8" />
                  </BarChart>
                </ResponsiveContainer>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Hourly Performance</Typography>
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={Object.keys(metrics.timingAnalysis.hourly).map(hour => ({
                    hour: `${hour}:00`,
                    pnl: metrics.timingAnalysis.hourly[hour]
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="hour" />
                    <YAxis />
                    <ChartTooltip formatter={(value) => [`$${value.toFixed(2)}`, 'P&L']} />
                    <Line type="monotone" dataKey="pnl" stroke="#8884d8" />
                  </LineChart>
                </ResponsiveContainer>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Learning Insights Section */}
        <Card>
          <CardHeader
            title="Learning Insights & Recommendations"
            avatar={<LightbulbIcon color="warning" />}
            subheader="Actionable insights to improve your trading performance"
          />
          <CardContent>
            {metrics.learningInsights.length > 0 ? (
              <Stack spacing={2}>
                {metrics.learningInsights.map((insight, index) => (
                  <Alert
                    key={index}
                    severity={insight.type}
                    action={
                      <Button color="inherit" size="small">
                        Apply
                      </Button>
                    }
                  >
                    <Typography variant="subtitle2" gutterBottom>
                      {insight.title}
                    </Typography>
                    <Typography variant="body2" gutterBottom>
                      {insight.message}
                    </Typography>
                    <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
                      💡 {insight.action}
                    </Typography>
                  </Alert>
                ))}
              </Stack>
            ) : (
              <Alert severity="info">
                Import more trade data to generate personalized insights and recommendations.
              </Alert>
            )}
          </CardContent>
        </Card>
      </Box>
    );
  };

  const ImportDialog = () => (
    <Dialog open={importDialog} onClose={() => setImportDialog(false)}>
      <DialogTitle>Import Trades from Alpaca</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info">
            This will import your trade history from Alpaca using your configured API keys.
          </Alert>
          
          {importStatus?.brokerStatus?.length > 0 && (
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>API Key Status</Typography>
                {importStatus.brokerStatus.map((broker, index) => (
                  <Box key={index} display="flex" alignItems="center" gap={1}>
                    {broker.keyActive ? (
                      <CheckCircleIcon color="success" />
                    ) : (
                      <CancelIcon color="error" />
                    )}
                    <Typography>
                      {broker.provider} - {broker.keyActive ? 'Active' : 'Inactive'}
                    </Typography>
                  </Box>
                ))}
              </CardContent>
            </Card>
          )}
          
          <LocalizationProvider dateAdapter={AdapterDateFns}>
            <MuiDatePicker
              label="Start Date"
              value={filters.startDate}
              onChange={(date) => setFilters(prev => ({ ...prev, startDate: date }))}
              renderInput={(params) => <TextField {...params} />}
            />
            <MuiDatePicker
              label="End Date"
              value={filters.endDate}
              onChange={(date) => setFilters(prev => ({ ...prev, endDate: date }))}
              renderInput={(params) => <TextField {...params} />}
            />
          </LocalizationProvider>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setImportDialog(false)}>Cancel</Button>
        <Button 
          onClick={handleImportTrades} 
          variant="contained"
          disabled={importing}
        >
          {importing ? <CircularProgress size={20} /> : 'Import Trades'}
        </Button>
      </DialogActions>
    </Dialog>
  );

  return (
    <Container maxWidth="xl">
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Trade History
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Comprehensive analysis of your trading activity with institutional-grade insights
        </Typography>
      </Box>

      {alertMessage && (
        <Alert 
          severity={alertMessage.severity} 
          onClose={() => setAlertMessage(null)}
          sx={{ mb: 2 }}
        >
          {alertMessage.message}
        </Alert>
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)}>
          <Tab label="Overview" icon={<AnalyticsIcon />} />
          <Tab label="Trade History" icon={<HistoryIcon />} />
          <Tab label="Analytics" icon={<AssessmentIcon />} />
        </Tabs>
      </Box>

      <Box sx={{ mb: 3 }}>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Timeframe</InputLabel>
          <Select
            value={timeframe}
            label="Timeframe"
            onChange={(e) => setTimeframe(e.target.value)}
          >
            <MenuItem value="1M">1 Month</MenuItem>
            <MenuItem value="3M">3 Months</MenuItem>
            <MenuItem value="6M">6 Months</MenuItem>
            <MenuItem value="1Y">1 Year</MenuItem>
            <MenuItem value="YTD">Year to Date</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {activeTab === 0 && analytics && <AnalyticsOverview />}
      {activeTab === 1 && <TradeTable />}
      {activeTab === 2 && <AdvancedAnalytics />}

      <ImportDialog />
    </Container>
  );
};

export default TradeHistory;