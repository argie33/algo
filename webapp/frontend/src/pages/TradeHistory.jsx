import React, { useState, useEffect } from 'react';
import { getApiConfig } from '../services/api';
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
  Sync as SyncIcon
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
    sortBy: 'execution_time',
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
      const { apiUrl } = getApiConfig();
      const response = await fetch(`${apiUrl}/api/trades/import/status`, {
        credentials: 'include'
      });
      const data = await response.json();
      if (data.success) {
        setImportStatus(data);
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

      const { apiUrl } = getApiConfig();
      const response = await fetch(`${apiUrl}/api/trades/history?${params}`, {
        credentials: 'include'
      });
      const data = await response.json();
      
      if (data.success) {
        setTrades(data.data.trades);
        setPagination(prev => ({
          ...prev,
          total: data.data.pagination.total,
          hasMore: data.data.pagination.hasMore
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
      const { apiUrl } = getApiConfig();
      const response = await fetch(`${apiUrl}/api/trades/analytics/overview?timeframe=${timeframe}`, {
        credentials: 'include'
      });
      const data = await response.json();
      if (data.success) {
        setAnalytics(data.data);
      }
    } catch (error) {
      console.error('Error fetching analytics:', error);
    }
  };

  const handleImportTrades = async () => {
    setImporting(true);
    try {
      const { apiUrl } = getApiConfig();
      const response = await fetch(`${apiUrl}/api/trades/import/alpaca`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          startDate: filters.startDate,
          endDate: filters.endDate,
          forceRefresh: true
        })
      });
      
      const data = await response.json();
      if (data.success) {
        setAlertMessage({ severity: 'success', message: 'Trades imported successfully!' });
        fetchTradeHistory();
        fetchAnalytics();
        fetchImportStatus();
        setImportDialog(false);
      } else {
        setAlertMessage({ severity: 'error', message: data.error || 'Import failed' });
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
      
      const { apiUrl } = getApiConfig();
      const response = await fetch(`${apiUrl}/api/trades/export?${params}`, {
        credentials: 'include'
      });
      
      if (format === 'csv') {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `trade_history_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
      } else {
        const data = await response.json();
        console.log('Export data:', data);
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
      {activeTab === 2 && (
        <Alert severity="info">
          Advanced analytics coming soon! This will include pattern recognition, 
          risk attribution, and performance benchmarking.
        </Alert>
      )}

      <ImportDialog />
    </Container>
  );
};

export default TradeHistory;