import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Alert,
  CircularProgress,
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
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  TablePagination
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  Timeline,
  Assessment
} from '@mui/icons-material';
import { formatCurrency, formatPercentage, formatNumber } from '../utils/formatters';

const TradingSignals = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [signalType, setSignalType] = useState('all');
  const [timeframe, setTimeframe] = useState('daily');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  const API_BASE = process.env.REACT_APP_API_URL || '';

  // Fetch buy/sell signals
  const { data: signalsData, isLoading: signalsLoading, error: signalsError } = useQuery({
    queryKey: ['tradingSignals', signalType, timeframe, page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        signal: signalType,
        timeframe,
        page: page + 1,
        limit: rowsPerPage
      });
      const response = await fetch(`${API_BASE}/trading/signals?${params}`);
      if (!response.ok) throw new Error('Failed to fetch signals');
      return response.json();
    },
    refetchInterval: 300000 // Refresh every 5 minutes
  });

  // Fetch swing trading signals
  const { data: swingData, isLoading: swingLoading } = useQuery({
    queryKey: ['swingSignals', page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page + 1,
        limit: rowsPerPage
      });
      const response = await fetch(`${API_BASE}/trading/swing-signals?${params}`);
      if (!response.ok) throw new Error('Failed to fetch swing signals');
      return response.json();
    },
    enabled: activeTab === 1,
    refetchInterval: 300000
  });

  // Fetch performance summary
  const { data: performanceData, isLoading: performanceLoading } = useQuery({
    queryKey: ['tradingPerformance'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/trading/performance`);
      if (!response.ok) throw new Error('Failed to fetch performance');
      return response.json();
    },
    refetchInterval: 600000 // Refresh every 10 minutes
  });

  const getSignalChip = (signal) => {
    const isBuy = signal === 'BUY';
    return (
      <Chip
        label={signal}
        size="small"
        icon={isBuy ? <TrendingUp /> : <TrendingDown />}
        sx={{
          backgroundColor: isBuy ? '#10B981' : '#DC2626',
          color: 'white',
          fontWeight: 'bold'
        }}
      />
    );
  };

  const getStatusChip = (status) => {
    const colors = {
      'TARGET_HIT': '#10B981',
      'STOP_LOSS_HIT': '#DC2626',
      'ACTIVE': '#3B82F6'
    };
    
    return (
      <Chip
        label={status.replace('_', ' ')}
        size="small"
        sx={{
          backgroundColor: colors[status] || '#6B7280',
          color: 'white',
          fontWeight: 'medium'
        }}
      />
    );
  };

  const PerformanceCard = ({ title, value, subtitle, icon, color }) => (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" mb={1}>
          {icon}
          <Typography variant="h6" ml={1}>{title}</Typography>
        </Box>
        <Typography variant="h4" sx={{ color, fontWeight: 'bold' }}>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
      </CardContent>
    </Card>
  );

  const BuySellSignalsTable = () => (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell>Company</TableCell>
            <TableCell>Signal</TableCell>
            <TableCell align="right">Signal Price</TableCell>
            <TableCell align="right">Current Price</TableCell>
            <TableCell align="right">Performance</TableCell>
            <TableCell>Date</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {signalsData?.data?.map((signal, index) => (
            <TableRow key={`${signal.symbol}-${index}`} hover>
              <TableCell>
                <Typography variant="body2" fontWeight="bold">
                  {signal.symbol}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2" noWrap>
                  {signal.company_name}
                </Typography>
              </TableCell>
              <TableCell>
                {getSignalChip(signal.signal)}
              </TableCell>
              <TableCell align="right">
                {formatCurrency(signal.price)}
              </TableCell>
              <TableCell align="right">
                {formatCurrency(signal.current_price)}
              </TableCell>
              <TableCell align="right">
                <Typography 
                  variant="body2" 
                  sx={{ 
                    color: signal.performance_percent >= 0 ? '#10B981' : '#DC2626',
                    fontWeight: 'medium'
                  }}
                >
                  {formatPercentage(signal.performance_percent / 100)}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {new Date(signal.date).toLocaleDateString()}
                </Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const SwingSignalsTable = () => (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell>Company</TableCell>
            <TableCell>Signal</TableCell>
            <TableCell align="right">Entry</TableCell>
            <TableCell align="right">Stop Loss</TableCell>
            <TableCell align="right">Target</TableCell>
            <TableCell align="right">Risk/Reward</TableCell>
            <TableCell align="right">Current</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Date</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {swingData?.data?.map((swing, index) => (
            <TableRow key={`${swing.symbol}-${index}`} hover>
              <TableCell>
                <Typography variant="body2" fontWeight="bold">
                  {swing.symbol}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2" noWrap>
                  {swing.company_name}
                </Typography>
              </TableCell>
              <TableCell>
                {getSignalChip(swing.signal)}
              </TableCell>
              <TableCell align="right">
                {formatCurrency(swing.entry_price)}
              </TableCell>
              <TableCell align="right">
                {formatCurrency(swing.stop_loss)}
              </TableCell>
              <TableCell align="right">
                {formatCurrency(swing.target_price)}
              </TableCell>
              <TableCell align="right">
                <Typography variant="body2" fontWeight="medium">
                  {swing.risk_reward_ratio ? `1:${swing.risk_reward_ratio.toFixed(1)}` : 'N/A'}
                </Typography>
              </TableCell>
              <TableCell align="right">
                {formatCurrency(swing.current_price)}
              </TableCell>
              <TableCell>
                {getStatusChip(swing.status)}
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {new Date(swing.date).toLocaleDateString()}
                </Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const isLoading = (activeTab === 0 ? signalsLoading : swingLoading) || performanceLoading;

  if (isLoading && !signalsData && !swingData) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Trading Signals
      </Typography>

      {/* Performance Summary */}
      <Grid container spacing={3} mb={4}>
        {performanceData?.performance?.map((perf) => (
          <Grid item xs={12} md={4} key={perf.signal}>
            <PerformanceCard
              title={`${perf.signal} Signals`}
              value={`${perf.win_rate?.toFixed(1)}%`}
              subtitle={`${perf.winning_trades}/${perf.total_signals} trades | Avg: ${formatPercentage(perf.avg_performance / 100)}`}
              icon={perf.signal === 'BUY' ? <TrendingUp /> : <TrendingDown />}
              color={perf.signal === 'BUY' ? '#10B981' : '#DC2626'}
            />
          </Grid>
        ))}
        <Grid item xs={12} md={4}>
          <PerformanceCard
            title="Analysis Period"
            value={`${performanceData?.period_days || 0} days`}
            subtitle="Signal performance tracking"
            icon={<Assessment />}
            color="#3B82F6"
          />
        </Grid>
      </Grid>

      {/* Tabs */}
      <Box mb={3}>
        <Tabs value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)}>
          <Tab label="Buy/Sell Signals" />
          <Tab label="Swing Trading" />
        </Tabs>
      </Box>

      {/* Filters */}
      {activeTab === 0 && (
        <Grid container spacing={2} mb={3}>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth>
              <InputLabel>Signal Type</InputLabel>
              <Select
                value={signalType}
                label="Signal Type"
                onChange={(e) => setSignalType(e.target.value)}
              >
                <MenuItem value="all">All Signals</MenuItem>
                <MenuItem value="buy">Buy Only</MenuItem>
                <MenuItem value="sell">Sell Only</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth>
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
          </Grid>
        </Grid>
      )}

      {/* Error Handling */}
      {(signalsError || (activeTab === 1 && swingData?.error)) && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load trading signals. Please try again later.
        </Alert>
      )}

      {/* Data Tables */}
      <Card>
        <CardContent>
          {activeTab === 0 ? <BuySellSignalsTable /> : <SwingSignalsTable />}
          
          <TablePagination
            component="div"
            count={activeTab === 0 ? (signalsData?.pagination?.total || 0) : (swingData?.pagination?.total || 0)}
            page={page}
            onPageChange={(e, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </CardContent>
      </Card>
    </Container>
  );
};

export default TradingSignals;
