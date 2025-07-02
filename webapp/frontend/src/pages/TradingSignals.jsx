import React, { useState, useMemo } from 'react'
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
  TablePagination,
  Badge,
  Tooltip,
  Switch,
  FormControlLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  IconButton,
  TextField,
  InputAdornment,
  Divider
} from '@mui/material'
import { TrendingUp, TrendingDown, Analytics, NewReleases, History, ExpandMore, FilterList, Close, Timeline, Search, Clear, ShowChart, HorizontalRule } from '@mui/icons-material'
import { formatCurrency, formatPercentage } from '../utils/formatters'
import { getApiConfig } from '../services/api'

// Simple logger replacement to prevent build errors
const logger = {
  success: (action, data, context) => console.log(`[TradingSignals] ${action}:`, { data, context }),
  error: (action, error, context) => console.error(`[TradingSignals] ${action}:`, { error: error?.message || error, context }),
  queryError: (query, error, context) => console.error(`[TradingSignals] Query ${query}:`, { error: error?.message || error, context })
};

function TradingSignals() {
  const { apiUrl: API_BASE } = getApiConfig();
  const [signalType, setSignalType] = useState('all');
  const [timeframe, setTimeframe] = useState('daily');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [showRecentOnly, setShowRecentOnly] = useState(true); // Changed default to true
  const [showHistoricalView, setShowHistoricalView] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [historicalDialogOpen, setHistoricalDialogOpen] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState('');
  const [searchInput, setSearchInput] = useState('');

  // Fetch historical data for selected symbol
  const { data: historicalData, isLoading: historicalLoading } = useQuery({
    queryKey: ['historicalSignals', selectedSymbol],
    queryFn: async () => {
      if (!selectedSymbol) return null;
      try {
        const response = await fetch(`${API_BASE}/api/trading/signals/daily?symbol=${selectedSymbol}&limit=50`);
        if (!response.ok) throw new Error('Failed to fetch historical data');
        return await response.json();
      } catch (err) {
        logger.error('fetchHistoricalSignals', err, { symbol: selectedSymbol });
        throw err;
      }
    },
    enabled: !!selectedSymbol && historicalDialogOpen,
    onError: (err) => logger.queryError('historicalSignals', err, { symbol: selectedSymbol })
  });
  // Helper functions for search
  const handleSearch = () => {
    setSymbolFilter(searchInput.trim());
    setPage(0);
  };

  const handleClearSearch = () => {
    setSearchInput('');
    setSymbolFilter('');
    setPage(0);
  };

  // Fetch buy/sell signals
  const { data: signalsData, isLoading: signalsLoading, error: signalsError } = useQuery({
    queryKey: ['tradingSignals', signalType, timeframe, page, rowsPerPage, symbolFilter, showRecentOnly],
    queryFn: async () => {
      try {
        const params = new URLSearchParams({
          signal_type: signalType === 'all' ? undefined : signalType,
          page: page + 1,
          limit: rowsPerPage,
          symbol: symbolFilter || undefined,
          latest_only: showRecentOnly ? 'true' : undefined
        });
        // Remove undefined values
        [...params.entries()].forEach(([key, value]) => {
          if (value === undefined || value === 'undefined') {
            params.delete(key);
          }
        });
        const url = `${API_BASE}/api/trading/signals/${timeframe}?${params}`;
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
        const url = `${API_BASE}/api/trading/performance`;
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
  // Helper function to check if signal is recent (within last 7 days)
  const isRecentSignal = (signalDate) => {
    if (!signalDate) return false;
    const today = new Date();
    const signal = new Date(signalDate);
    const diffTime = Math.abs(today - signal);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays <= 7;
  };

  const getSignalChip = (signal, signalDate) => {
    const isBuy = signal === 'Buy';
    const isSell = signal === 'Sell';
    const isNone = signal === 'None' || !signal;
    const isRecent = isRecentSignal(signalDate);
    
    return (
      <Badge
        badgeContent={isRecent ? <NewReleases sx={{ fontSize: 12 }} /> : 0}
        color="secondary"
        overlap="circular"
      >
        <Chip
          label={signal || 'None'}
          size="small"
          icon={isBuy ? <TrendingUp /> : isSell ? <TrendingDown /> : <HorizontalRule />}
          sx={{
            backgroundColor: isBuy ? '#10B981' : isSell ? '#DC2626' : '#9CA3AF',
            color: 'white',
            fontWeight: 'bold',
            ...(isRecent && {
              boxShadow: '0 0 10px rgba(59, 130, 246, 0.5)',
              animation: 'pulse 2s infinite'
            })
          }}
        />
      </Badge>
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

  // Calculate summary statistics
  const summaryStats = useMemo(() => {
    if (!signalsData?.data) return null;
    
    const signals = signalsData.data;
    const totalSignals = signals.length;
    const recentSignals = signals.filter(s => isRecentSignal(s.date)).length;
    const buySignals = signals.filter(s => s.signal === 'Buy').length;
    const sellSignals = signals.filter(s => s.signal === 'Sell').length;
    
    // Find top performing sectors
    const sectorCounts = {};
    signals.forEach(s => {
      if (s.sector) {
        sectorCounts[s.sector] = (sectorCounts[s.sector] || 0) + 1;
      }
    });
    const topSector = Object.entries(sectorCounts).sort((a, b) => b[1] - a[1])[0];
    
    return {
      totalSignals,
      recentSignals,
      buySignals,
      sellSignals,
      topSector: topSector ? topSector[0] : null,
      topSectorCount: topSector ? topSector[1] : 0
    };
  }, [signalsData]);

  const PerformanceCard = ({ title, value, subtitle, icon, color, isHighlight = false }) => (
    <Card sx={{ 
      ...(isHighlight && {
        border: '2px solid #3B82F6',
        boxShadow: '0 4px 20px rgba(59, 130, 246, 0.15)'
      })
    }}>
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
  // Filter data based on recent-only setting
  const filteredSignals = useMemo(() => {
    if (!signalsData?.data) return [];
    
    let filtered = signalsData.data;
    
    // Apply recent-only filter if enabled
    if (showRecentOnly) {
      filtered = filtered.filter(signal => isRecentSignal(signal.date));
    }
    
    // Remove duplicates by symbol, keeping the most recent
    if (showRecentOnly) {
      const symbolMap = new Map();
      filtered.forEach(signal => {
        const existing = symbolMap.get(signal.symbol);
        if (!existing || new Date(signal.date) > new Date(existing.date)) {
          symbolMap.set(signal.symbol, signal);
        }
      });
      filtered = Array.from(symbolMap.values());
    }
    
    return filtered;
  }, [signalsData, showRecentOnly]);

  // --- Table for Buy/Sell signals, matching backend fields ---
  const BuySellSignalsTable = () => (
    <TableContainer component={Paper} elevation={0}>
      <Table>
        <TableHead>
          <TableRow sx={{ backgroundColor: 'grey.50' }}>
            <TableCell sx={{ fontWeight: 'bold' }}>Symbol</TableCell>
            <TableCell sx={{ fontWeight: 'bold' }}>Company</TableCell>
            <TableCell sx={{ fontWeight: 'bold' }}>Sector</TableCell>
            <TableCell sx={{ fontWeight: 'bold' }}>Signal</TableCell>
            <TableCell align="right" sx={{ fontWeight: 'bold' }}>Current Price</TableCell>
            <TableCell align="right" sx={{ fontWeight: 'bold' }}>Market Cap</TableCell>
            <TableCell align="right" sx={{ fontWeight: 'bold' }}>P/E</TableCell>
            <TableCell align="right" sx={{ fontWeight: 'bold' }}>Dividend Yield</TableCell>
            <TableCell sx={{ fontWeight: 'bold' }}>Date</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {filteredSignals?.map((signal, index) => (
            <TableRow 
              key={`${signal.symbol}-${index}`} 
              hover
              sx={{
                '&:hover': { backgroundColor: 'action.hover' },
                ...(isRecentSignal(signal.date) && {
                  backgroundColor: 'rgba(59, 130, 246, 0.05)',
                  borderLeft: '4px solid #3B82F6'
                })
              }}
            >
              <TableCell>
                <Button
                  variant="text"
                  size="small"
                  sx={{ fontWeight: 'bold', minWidth: 'auto', p: 0.5 }}
                  onClick={() => {
                    setSelectedSymbol(signal.symbol);
                    setHistoricalDialogOpen(true);
                  }}
                >
                  {signal.symbol}
                </Button>
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
                <Tooltip title={isRecentSignal(signal.date) ? "New signal within last 7 days" : "Historical signal"}>
                  <Box>{getSignalChip(signal.signal, signal.date)}</Box>
                </Tooltip>
              </TableCell>
              <TableCell align="right">
                {formatCurrency(signal.current_price)}
              </TableCell>
              <TableCell align="right">
                {signal.market_cap ? `$${(+signal.market_cap).toLocaleString()}` : '—'}
              </TableCell>
              <TableCell align="right">
                {signal.trailing_pe && !isNaN(Number(signal.trailing_pe)) ? Number(signal.trailing_pe).toFixed(2) : '—'}
              </TableCell>
              <TableCell align="right">
                {signal.dividend_yield ? formatPercentage(signal.dividend_yield) : '—'}
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {signal.date ? new Date(signal.date).toLocaleDateString() : ''}
                </Typography>
              </TableCell>
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
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <Typography variant="h4" component="h1" fontWeight="bold">
          Trading Signals
        </Typography>
        <Box display="flex" gap={2}>
          <Button
            variant="outlined"
            startIcon={<ShowChart />}
            onClick={() => setShowHistoricalView(!showHistoricalView)}
          >
            {showHistoricalView ? 'Simple View' : 'Advanced View'}
          </Button>
        </Box>
      </Box>

      {/* Enhanced Performance Summary */}
      <Grid container spacing={3} mb={4}>
        {/* Active Signals Summary - Most Important */}
        {summaryStats && (
          <Grid item xs={12} md={3}>
            <PerformanceCard
              title="Active Signals"
              value={summaryStats.totalSignals}
              subtitle={`${summaryStats.recentSignals} new in last 7 days`}
              icon={<Badge badgeContent={summaryStats.recentSignals} color="secondary"><Analytics /></Badge>}
              color="#3B82F6"
              isHighlight={summaryStats.recentSignals > 0}
            />
          </Grid>
        )}
        
        {performanceData?.performance?.map((perf) => (
          <Grid item xs={12} md={3} key={perf.signal}>
            <PerformanceCard
              title={`${perf.signal} Win Rate`}
              value={`${perf.win_rate?.toFixed(1)}%`}
              subtitle={`${perf.winning_trades}/${perf.total_signals} trades | Avg: ${formatPercentage(perf.avg_performance / 100)}`}
              icon={perf.signal === 'BUY' ? <TrendingUp /> : <TrendingDown />}
              color={perf.signal === 'BUY' ? '#10B981' : '#DC2626'}
            />
          </Grid>
        ))}
        
        {summaryStats?.topSector && (
          <Grid item xs={12} md={3}>
            <PerformanceCard
              title="Top Sector"
              value={summaryStats.topSector}
              subtitle={`${summaryStats.topSectorCount} signals`}
              icon={<TrendingUp />}
              color="#8B5CF6"
            />
          </Grid>
        )}
      </Grid>

      {/* Filters and Search */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <Card sx={{ position: 'sticky', top: 20 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                <FilterList sx={{ mr: 1 }} />
                Filters
              </Typography>
              <Divider sx={{ mb: 2 }} />
              
              {/* Search */}
              <TextField
                fullWidth
                size="small"
                placeholder="Search symbols..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  ),
                  endAdornment: searchInput && (
                    <InputAdornment position="end">
                      <IconButton size="small" onClick={handleClearSearch}>
                        <Clear />
                      </IconButton>
                    </InputAdornment>
                  )
                }}
                sx={{ mb: 2 }}
              />
              
              <Button
                fullWidth
                variant="contained"
                onClick={handleSearch}
                sx={{ mb: 3 }}
              >
                Search
              </Button>

              {/* Signal Type Filter */}
              <FormControl fullWidth sx={{ mb: 2 }}>
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

              {/* Timeframe Filter */}
              <FormControl fullWidth sx={{ mb: 2 }}>
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

              {/* Toggle Switches */}
              <FormControlLabel
                control={
                  <Switch
                    checked={showRecentOnly}
                    onChange={(e) => setShowRecentOnly(e.target.checked)}
                  />
                }
                label="Latest Only"
                sx={{ mb: 1 }}
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={showHistoricalView}
                    onChange={(e) => setShowHistoricalView(e.target.checked)}
                  />
                }
                label="Historical View"
              />
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={9}>

      {/* Error Handling */}
      {signalsError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load trading signals. Please check your data sources and try again.
          <br /><b>Error:</b> {signalsError.message}
          <br /><small>Debug endpoint: <code>{API_BASE}/trading/debug</code></small>
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
        </Grid>
      </Grid>

      {/* Historical Data Dialog */}
      <Dialog
        open={historicalDialogOpen}
        onClose={() => setHistoricalDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" alignItems="center" justifyContent="space-between">
            <Box display="flex" alignItems="center">
              <Timeline sx={{ mr: 1 }} />
              <Typography variant="h6">
                {selectedSymbol} - Historical Signals
              </Typography>
            </Box>
            <IconButton
              onClick={() => setHistoricalDialogOpen(false)}
              size="small"
            >
              <Close />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent>
          {historicalLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell>Signal</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">Buy Level</TableCell>
                    <TableCell align="right">Stop Level</TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {historicalData?.data?.map((signal, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        {signal.date ? new Date(signal.date).toLocaleDateString() : ''}
                      </TableCell>
                      <TableCell>
                        {getSignalChip(signal.signal, signal.date)}
                      </TableCell>
                      <TableCell align="right">
                        {formatCurrency(signal.current_price)}
                      </TableCell>
                      <TableCell align="right">
                        {signal.buylevel ? formatCurrency(signal.buylevel) : '—'}
                      </TableCell>
                      <TableCell align="right">
                        {signal.stoplevel ? formatCurrency(signal.stoplevel) : '—'}
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={signal.inposition ? 'In Position' : 'Closed'}
                          size="small"
                          color={signal.inposition ? 'primary' : 'default'}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHistoricalDialogOpen(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}

export default TradingSignals;
