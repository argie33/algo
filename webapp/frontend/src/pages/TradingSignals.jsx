import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  TablePagination
} from '@mui/material'
import { TrendingUp, TrendingDown, Analytics } from '@mui/icons-material'
import { formatCurrency, formatPercentage } from '../utils/formatters'

// Simple logger replacement to prevent build errors
const logger = {
  success: (action, data, context) => console.log(`[TradingSignals] ${action}:`, { data, context }),
  error: (action, error, context) => console.error(`[TradingSignals] ${action}:`, { error: error?.message || error, context }),
  queryError: (query, error, context) => console.error(`[TradingSignals] Query ${query}:`, { error: error?.message || error, context })
};

function TradingSignals() {
  const [signalType, setSignalType] = useState('all');
  const [timeframe, setTimeframe] = useState('daily');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const API_BASE = import.meta.env.VITE_API_URL || '';
  // Fetch buy/sell signals
  const { data: signalsData, isLoading: signalsLoading, error: signalsError } = useQuery({
    queryKey: ['tradingSignals', signalType, timeframe, page, rowsPerPage],
    queryFn: async () => {
      try {
        const params = new URLSearchParams({
          signal_type: signalType === 'all' ? undefined : signalType,
          page: page + 1,
          limit: rowsPerPage
        });
        // Remove undefined values
        [...params.entries()].forEach(([key, value]) => {
          if (value === undefined || value === 'undefined') {
            params.delete(key);
          }
        });
        const url = `${API_BASE}/trading/signals/${timeframe}?${params}`;
        logger.success('fetchTradingSignals', null, { url, signalType, timeframe });
        
        const response = await fetch(url);
        if (!response.ok) {
          const error = new Error(`Failed to fetch signals (${response.status})`);
          logger.error('fetchTradingSignals', error, {
            url,
            status: response.status,
            statusText: response.statusText
          });
          throw error;
        }
        
        const result = await response.json();
        logger.success('fetchTradingSignals', result, {
          resultCount: result?.data?.length || 0,
          signalType,
          timeframe,
          page: page + 1
        });
        return result;
      } catch (err) {
        logger.error('fetchTradingSignals', err, { signalType, timeframe, page: page + 1, rowsPerPage });
        throw err;
      }
    },
    refetchInterval: 300000, // Refresh every 5 minutes
    onError: (err) => logger.queryError('tradingSignals', err, { signalType, timeframe })
  });

  // Fetch performance summary
  const { data: performanceData, isLoading: performanceLoading } = useQuery({
    queryKey: ['tradingPerformance'],
    queryFn: async () => {
      try {
        const url = `${API_BASE}/trading/performance`;
        logger.success('fetchTradingPerformance', null, { url });
        
        const response = await fetch(url);
        if (!response.ok) {
          const error = new Error(`Failed to fetch performance (${response.status})`);
          logger.error('fetchTradingPerformance', error, {
            url,
            status: response.status,
            statusText: response.statusText
          });
          throw error;
        }
        
        const result = await response.json();
        logger.success('fetchTradingPerformance', result);
        return result;
      } catch (err) {
        logger.error('fetchTradingPerformance', err);
        throw err;
      }
    },
    refetchInterval: 600000, // Refresh every 10 minutes
    onError: (err) => logger.queryError('tradingPerformance', err)
  });
  const getSignalChip = (signal) => {
    const isBuy = signal === 'Buy';
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
  // --- Table for Buy/Sell signals, matching backend fields ---
  const BuySellSignalsTable = () => (
    <TableContainer component={Paper} elevation={0}>
      <Table>
        <TableHead>
          <TableRow sx={{ backgroundColor: 'grey.50' }}>
            <TableCell>Symbol</TableCell>
            <TableCell>Company</TableCell>
            <TableCell>Sector</TableCell>
            <TableCell>Signal</TableCell>
            <TableCell align="right">Current Price</TableCell>
            <TableCell align="right">Market Cap</TableCell>
            <TableCell align="right">P/E</TableCell>
            <TableCell align="right">Dividend Yield</TableCell>
            <TableCell>Date</TableCell>
            {/* Add more columns here if your backend provides them */}
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
                <Typography variant="body2" noWrap>
                  {signal.sector}
                </Typography>
              </TableCell>
              <TableCell>
                {getSignalChip(signal.signal)}
              </TableCell>
              <TableCell align="right">
                {formatCurrency(signal.current_price)}
              </TableCell>
              <TableCell align="right">
                {signal.market_cap ? `$${(+signal.market_cap).toLocaleString()}` : '—'}
              </TableCell>
              <TableCell align="right">
                {signal.trailing_pe ? signal.trailing_pe.toFixed(2) : '—'}
              </TableCell>
              <TableCell align="right">
                {signal.dividend_yield ? formatPercentage(signal.dividend_yield) : '—'}
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {signal.date ? new Date(signal.date).toLocaleDateString() : ''}
                </Typography>
              </TableCell>
              {/* Add more cells here if your backend provides them */}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const isLoading = signalsLoading || performanceLoading;

  if (isLoading && !signalsData) {
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
            icon={<Analytics />}
            color="#3B82F6"
          />
        </Grid>
      </Grid>

      {/* Filters */}
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

      {/* Error Handling */}
      {signalsError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load trading signals. Please try again later.<br />
          <b>Error:</b> {signalsError.message}<br />
          {signalsError.stack && <span style={{ fontSize: 12 }}>{signalsError.stack.split('\n')[0]}</span>}
          <br />API URL: <code>{API_BASE}/trading/signals/{timeframe}</code>
          <br /><small>Check the API debug endpoint at: <code>{API_BASE}/trading/debug</code> for table status</small>
        </Alert>
      )}

      {/* Data Table */}
      <Card>
        <CardContent>
          <BuySellSignalsTable />
          <TablePagination
            component="div"
            count={signalsData?.pagination?.total || 0}
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
}

export default TradingSignals;
