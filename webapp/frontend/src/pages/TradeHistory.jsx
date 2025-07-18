import React, { useState, useEffect } from 'react';
// Trade History - fully integrated with real broker API data via user API keys
// Updated: 2025-07-12 - Enhanced real-time trade analytics using broker credentials
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
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12} md={3}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center">
              <AssessmentIcon color="primary" sx={{ mr: 1 }} />
              <div  variant="h6">Total Trades</div>
            </div>
            <div  variant="h4" color="primary">
              {analytics?.overview?.totalTrades || 0}
            </div>
          </div>
        </div>
      </div>
      <div className="grid" item xs={12} md={3}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center">
              <TrendingUpIcon color="success" sx={{ mr: 1 }} />
              <div  variant="h6">Win Rate</div>
            </div>
            <div  variant="h4" color="success.main">
              {analytics?.overview?.winRate || 0}%
            </div>
          </div>
        </div>
      </div>
      <div className="grid" item xs={12} md={3}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center">
              <AccountBalanceIcon color="info" sx={{ mr: 1 }} />
              <div  variant="h6">Total P&L</div>
            </div>
            <div  variant="h4" color={getPnLColor(analytics?.overview?.totalPnl)}>
              {formatCurrency(analytics?.overview?.totalPnl)}
            </div>
          </div>
        </div>
      </div>
      <div className="grid" item xs={12} md={3}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center">
              <TimelineIcon color="warning" sx={{ mr: 1 }} />
              <div  variant="h6">Avg ROI</div>
            </div>
            <div  variant="h4" color={getPnLColor(analytics?.overview?.avgRoi)}>
              {formatPercent(analytics?.overview?.avgRoi)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const TradeTable = () => (
    <div className="bg-white shadow-md rounded-lg">
      <div className="bg-white shadow-md rounded-lg"Header 
        title="Trade History"
        action={
          <div  display="flex" gap={1}>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              variant="outlined" 
              startIcon={<FilterIcon />}
              onClick={() => setImportDialog(true)}
            >
              Filters
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              variant="outlined" 
              startIcon={<⬇  />}
              onClick={() => handleExport('csv')}
            >
              Export
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              variant="contained" 
              startIcon={<SyncIcon />}
              onClick={() => setImportDialog(true)}
            >
              Import
            </button>
          </div>
        }
      />
      <div className="bg-white shadow-md rounded-lg"Content>
        {loading ? (
          <div  display="flex" justifyContent="center" p={3}>
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
          </div>
        ) : (
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Date</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Type</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Quantity</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Total P&L</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">ROI</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Pattern</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sector</td>
                </tr>
              </thead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                {trades.map((trade, index) => (
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index}>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      {new Date(trade.execution_time).toLocaleDateString()}
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      <div  variant="body2" fontWeight="bold">
                        {trade.symbol}
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={trade.side} 
                        color={getTradeTypeColor(trade.side)}
                        size="small"
                      />
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      {trade.quantity}
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      {formatCurrency(trade.price)}
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  color={getPnLColor(trade.net_pnl)}>
                        {formatCurrency(trade.net_pnl)}
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  color={getPnLColor(trade.return_percentage)}>
                        {formatPercent(trade.return_percentage)}
                      </div>
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      {trade.trade_pattern_type && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={trade.trade_pattern_type} 
                          variant="outlined" 
                          size="small"
                        />
                      )}
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      {trade.sector && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={trade.sector} 
                          color="info"
                          variant="outlined" 
                          size="small"
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        
        {pagination.hasMore && (
          <div  display="flex" justifyContent="center" mt={2}>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              variant="outlined" 
              onClick={() => setPagination(prev => ({ ...prev, page: prev.page + 1 }))}
            >
              Load More
            </button>
          </div>
        )}
      </div>
    </div>
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
      <div>
        {/* Pattern Recognition Section */}
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Header
            title="Pattern Recognition Analysis"
            avatar={<PsychologyIcon color="primary" />}
            subheader="Identify which trading patterns work best for you"
          />
          <div className="bg-white shadow-md rounded-lg"Content>
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12} md={6}>
                <div  variant="h6" gutterBottom>Pattern Performance</div>
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
              </div>
              <div className="grid" item xs={12} md={6}>
                <div  variant="h6" gutterBottom>Pattern Frequency</div>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={Object.keys(metrics?.patternAnalysis?.frequency || {}).map((key, index) => ({
                        name: key,
                        value: metrics?.patternAnalysis?.frequency?.[key] || 0,
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
              </div>
            </div>
          </div>
        </div>

        {/* Risk Attribution Section */}
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Header
            title="Risk Attribution Analysis"
            avatar={<WarningIcon color="warning" />}
            subheader="Understand your risk/reward profile and improve risk management"
          />
          <div className="bg-white shadow-md rounded-lg"Content>
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={6} md={3}>
                <div className="bg-white shadow-md rounded-lg" variant="outlined">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  color="text.secondary" gutterBottom>Profit Factor</div>
                    <div  variant="h4" color={metrics.riskAttribution.profitFactor >= 1.5 ? 'success.main' : 'error.main'}>
                      {metrics.riskAttribution.profitFactor.toFixed(2)}
                    </div>
                    <div  variant="body2">
                      {metrics.riskAttribution.profitFactor >= 1.5 ? 'Good' : 'Needs Improvement'}
                    </div>
                  </div>
                </div>
              </div>
              <div className="grid" item xs={6} md={3}>
                <div className="bg-white shadow-md rounded-lg" variant="outlined">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  color="text.secondary" gutterBottom>Expectancy</div>
                    <div  variant="h4" color={metrics.riskAttribution.expectancy >= 0 ? 'success.main' : 'error.main'}>
                      ${metrics.riskAttribution.expectancy.toFixed(2)}
                    </div>
                    <div  variant="body2">Per Trade</div>
                  </div>
                </div>
              </div>
              <div className="grid" item xs={6} md={3}>
                <div className="bg-white shadow-md rounded-lg" variant="outlined">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  color="text.secondary" gutterBottom>Avg Win</div>
                    <div  variant="h4" color="success.main">
                      ${metrics.riskAttribution.avgWin.toFixed(2)}
                    </div>
                    <div  variant="body2">Average</div>
                  </div>
                </div>
              </div>
              <div className="grid" item xs={6} md={3}>
                <div className="bg-white shadow-md rounded-lg" variant="outlined">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  color="text.secondary" gutterBottom>Avg Loss</div>
                    <div  variant="h4" color="error.main">
                      ${metrics.riskAttribution.avgLoss.toFixed(2)}
                    </div>
                    <div  variant="body2">Average</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Performance Benchmarking Section */}
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Header
            title="Performance Benchmarking"
            avatar={<CompareArrowsIcon color="info" />}
            subheader="Compare performance across sectors and identify strengths"
          />
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>Sector Performance</div>
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
          </div>
        </div>

        {/* Timing Analysis Section */}
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Header
            title="Trade Timing Analysis"
            avatar={<ScheduleIcon color="primary" />}
            subheader="Discover optimal trading times and patterns"
          />
          <div className="bg-white shadow-md rounded-lg"Content>
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12} md={6}>
                <div  variant="h6" gutterBottom>Daily Performance</div>
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
              </div>
              <div className="grid" item xs={12} md={6}>
                <div  variant="h6" gutterBottom>Hourly Performance</div>
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
              </div>
            </div>
          </div>
        </div>

        {/* Learning Insights Section */}
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Header
            title="Learning Insights & Recommendations"
            avatar={<LightbulbIcon color="warning" />}
            subheader="Actionable insights to improve your trading performance"
          />
          <div className="bg-white shadow-md rounded-lg"Content>
            {metrics.learningInsights.length > 0 ? (
              <div className="flex flex-col space-y-2" spacing={2}>
                {metrics.learningInsights.map((insight, index) => (
                  <div className="p-4 rounded-md bg-blue-50 border border-blue-200"
                    key={index}
                    severity={insight.type}
                    action={
                      <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" color="inherit" size="small">
                        Apply
                      </button>
                    }
                  >
                    <div  variant="subtitle2" gutterBottom>
                      {insight.title}
                    </div>
                    <div  variant="body2" gutterBottom>
                      {insight.message}
                    </div>
                    <div  variant="body2" sx={{ fontStyle: 'italic' }}>
                      💡 {insight.action}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
                Import more trade data to generate personalized insights and recommendations.
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const ImportDialog = () => (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={importDialog} onClose={() => setImportDialog(false)}>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Import Trades from Alpaca</h2>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
        <div className="flex flex-col space-y-2" spacing={2} sx={{ mt: 1 }}>
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
            This will import your trade history from Alpaca using your configured API keys.
          </div>
          
          {importStatus?.brokerStatus?.length > 0 && (
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>API Key Status</div>
                {importStatus.brokerStatus.map((broker, index) => (
                  <div  key={index} display="flex" alignItems="center" gap={1}>
                    {broker.keyActive ? (
                      <CheckCircleIcon color="success" />
                    ) : (
                      <CancelIcon color="error" />
                    )}
                    <div>
                      {broker.provider} - {broker.keyActive ? 'Active' : 'Inactive'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          <LocalizationProvider dateAdapter={AdapterDateFns}>
            <MuiDatePicker
              label="Start Date"
              value={filters.startDate}
              onChange={(date) => setFilters(prev => ({ ...prev, startDate: date }))}
              renderInput={(params) => <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" {...params} />}
            />
            <MuiDatePicker
              label="End Date"
              value={filters.endDate}
              onChange={(date) => setFilters(prev => ({ ...prev, endDate: date }))}
              renderInput={(params) => <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" {...params} />}
            />
          </LocalizationProvider>
        </div>
      </div>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setImportDialog(false)}>Cancel</button>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
          onClick={handleImportTrades} 
          variant="contained"
          disabled={importing}
        >
          {importing ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : 'Import Trades'}
        </button>
      </div>
    </div>
  );

  return (
    <div className="container mx-auto" maxWidth="xl">
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" component="h1" gutterBottom>
          Trade History
        </div>
        <div  variant="body1" color="text.secondary">
          Comprehensive analysis of your trading activity with institutional-grade insights
        </div>
      </div>

      {alertMessage && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity={alertMessage.severity} 
          onClose={() => setAlertMessage(null)}
          sx={{ mb: 2 }}
        >
          {alertMessage.message}
        </div>
      )}

      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={activeTab} onChange={(e, v) => setActiveTab(v)}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Overview" icon={<AnalyticsIcon />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Trade History" icon={<HistoryIcon />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Analytics" icon={<AssessmentIcon />} />
        </div>
      </div>

      <div  sx={{ mb: 3 }}>
        <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
          <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
          <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={timeframe}
            label="Timeframe"
            onChange={(e) => setTimeframe(e.target.value)}
          >
            <option  value="1M">1 Month</option>
            <option  value="3M">3 Months</option>
            <option  value="6M">6 Months</option>
            <option  value="1Y">1 Year</option>
            <option  value="YTD">Year to Date</option>
          </select>
        </div>
      </div>

      {activeTab === 0 && analytics && <AnalyticsOverview />}
      {activeTab === 1 && <TradeTable />}
      {activeTab === 2 && <AdvancedAnalytics />}

      <ImportDialog />
    </div>
  );
};

export default TradeHistory;