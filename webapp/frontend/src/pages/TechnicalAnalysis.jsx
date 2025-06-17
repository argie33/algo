import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createComponentLogger } from '../utils/errorLogger';
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
  CircularProgress,
  Alert,
  TextField,
  Button,  Accordion,
  AccordionSummary,
  AccordionDetails,
  Pagination
} from '@mui/material';
import {
  ExpandMore,
  Search
} from '@mui/icons-material';
import { formatNumber, formatDate } from '../utils/formatters';
import { getTechnicalData } from '../services/api';

// Use centralized error logging (logger will be defined in component)

function TechnicalAnalysis() {
  const logger = createComponentLogger('TechnicalAnalysis');
  
  const [timeframe, setTimeframe] = useState('daily');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');  // Fetch technical data - always use getTechnicalData for consistent data structure
  const { data: technicalData, isLoading, error, refetch } = useQuery({
    queryKey: ['technicalAnalysis', timeframe, symbolFilter, page],
    queryFn: () => {
      return getTechnicalData(timeframe, { 
        symbol: symbolFilter || undefined, // Only include symbol if filtering
        limit: symbolFilter ? 50 : 25, // More data for specific symbols
        page: page
      });
    },
    onError: (error) => logger.queryError('technicalAnalysis', error, { timeframe, symbolFilter, page }),
    refetchInterval: 300000, // Refresh every 5 minutes
    retry: 2,
    staleTime: 60000 // Consider data fresh for 1 minute
  });

  const handleSearch = () => {
    setSymbolFilter(searchInput.trim());
    setPage(1); // Reset to first page when searching
  };

  const handleClearSearch = () => {
    setSearchInput('');
    setSymbolFilter('');
    setPage(1);
  };

  const handleTimeframeChange = (newTimeframe) => {
    setTimeframe(newTimeframe);
    setPage(1); // Reset to first page when changing timeframe
  };

  const getSignalColor = (value, type) => {
    if (value === null || value === undefined) return 'grey.500';
    
    switch (type) {
      case 'rsi':
        if (value > 70) return 'error.main'; // Overbought
        if (value < 30) return 'success.main'; // Oversold
        return 'warning.main';
      case 'macd':
        return value > 0 ? 'success.main' : 'error.main';
      case 'adx':
        if (value > 25) return 'success.main'; // Strong trend
        return 'warning.main';
      default:
        return 'grey.500';
    }
  };

  const TechnicalIndicatorCard = ({ title, value, description, type, unit = '' }) => (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Typography variant="h6" component="h3" gutterBottom>
          {title}
        </Typography>
        <Typography 
          variant="h4" 
          component="p" 
          sx={{ 
            color: getSignalColor(value, type),
            fontWeight: 'bold',
            mb: 1
          }}
        >
          {value !== null && value !== undefined ? `${formatNumber(value)}${unit}` : 'N/A'}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {description}
        </Typography>
      </CardContent>
    </Card>
  );

  const ComprehensiveTechnicalTable = () => (
    <TableContainer component={Paper} elevation={0} sx={{ maxHeight: 600, overflow: 'auto' }}>
      <Table stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>Symbol</TableCell>
            <TableCell sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>Date</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>RSI</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>MACD</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>MACD Signal</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>MACD Hist</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>ADX</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>ATR</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>MFI</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>ROC</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>MOM</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>BB Upper</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>BB Middle</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>BB Lower</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>SMA 10</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>SMA 20</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>SMA 50</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>SMA 150</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>SMA 200</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>EMA 4</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>EMA 9</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>EMA 21</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>A/D</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>CMF</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>TD Seq</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>TD Combo</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>MW</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>DM</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>Pivot H</TableCell>
            <TableCell align="right" sx={{ backgroundColor: 'grey.50', fontWeight: 'bold' }}>Pivot L</TableCell>
          </TableRow>
        </TableHead>        <TableBody>
          {Array.isArray(technicalData?.data?.data) ? technicalData.data.data.map((row, index) => (
            <TableRow key={`${row.symbol}-${index}`} hover>
              <TableCell>
                <Typography variant="body2" fontWeight="bold">
                  {row.symbol}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {formatDate(row.date)}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography 
                  variant="body2" 
                  sx={{ color: getSignalColor(row.rsi, 'rsi') }}
                >
                  {row.rsi ? formatNumber(row.rsi) : 'N/A'}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography 
                  variant="body2"
                  sx={{ color: getSignalColor(row.macd, 'macd') }}
                >
                  {row.macd ? formatNumber(row.macd, 4) : 'N/A'}
                </Typography>
              </TableCell>
              <TableCell align="right">{row.macd_signal ? formatNumber(row.macd_signal, 4) : 'N/A'}</TableCell>
              <TableCell align="right">{row.macd_hist ? formatNumber(row.macd_hist, 4) : 'N/A'}</TableCell>
              <TableCell align="right">
                <Typography 
                  variant="body2"
                  sx={{ color: getSignalColor(row.adx, 'adx') }}
                >
                  {row.adx ? formatNumber(row.adx) : 'N/A'}
                </Typography>
              </TableCell>
              <TableCell align="right">{row.atr ? formatNumber(row.atr) : 'N/A'}</TableCell>
              <TableCell align="right">{row.mfi ? formatNumber(row.mfi) : 'N/A'}</TableCell>
              <TableCell align="right">{row.roc ? formatNumber(row.roc) : 'N/A'}</TableCell>
              <TableCell align="right">{row.mom ? formatNumber(row.mom) : 'N/A'}</TableCell>
              <TableCell align="right">{row.bbands_upper ? formatNumber(row.bbands_upper) : 'N/A'}</TableCell>
              <TableCell align="right">{row.bbands_middle ? formatNumber(row.bbands_middle) : 'N/A'}</TableCell>
              <TableCell align="right">{row.bbands_lower ? formatNumber(row.bbands_lower) : 'N/A'}</TableCell>
              <TableCell align="right">{row.sma_10 ? formatNumber(row.sma_10) : 'N/A'}</TableCell>
              <TableCell align="right">{row.sma_20 ? formatNumber(row.sma_20) : 'N/A'}</TableCell>
              <TableCell align="right">{row.sma_50 ? formatNumber(row.sma_50) : 'N/A'}</TableCell>
              <TableCell align="right">{row.sma_150 ? formatNumber(row.sma_150) : 'N/A'}</TableCell>
              <TableCell align="right">{row.sma_200 ? formatNumber(row.sma_200) : 'N/A'}</TableCell>
              <TableCell align="right">{row.ema_4 ? formatNumber(row.ema_4) : 'N/A'}</TableCell>
              <TableCell align="right">{row.ema_9 ? formatNumber(row.ema_9) : 'N/A'}</TableCell>
              <TableCell align="right">{row.ema_21 ? formatNumber(row.ema_21) : 'N/A'}</TableCell>
              <TableCell align="right">{row.ad ? formatNumber(row.ad) : 'N/A'}</TableCell>              <TableCell align="right">{row.cmf ? formatNumber(row.cmf, 4) : 'N/A'}</TableCell>
              <TableCell align="right">{row.td_sequential ? formatNumber(row.td_sequential) : 'N/A'}</TableCell>
              <TableCell align="right">{row.td_combo ? formatNumber(row.td_combo) : 'N/A'}</TableCell>
              <TableCell align="right">{row.marketwatch ? formatNumber(row.marketwatch) : 'N/A'}</TableCell>
              <TableCell align="right">{row.dm ? formatNumber(row.dm) : 'N/A'}</TableCell>
              <TableCell align="right">{row.pivot_high ? formatNumber(row.pivot_high) : 'N/A'}</TableCell>
              <TableCell align="right">{row.pivot_low ? formatNumber(row.pivot_low) : 'N/A'}</TableCell>
            </TableRow>
          )) : (
            <TableRow>
              <TableCell colSpan={26} align="center">
                <Typography variant="body2" color="text.secondary">
                  No technical data available
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableContainer>
  );
  if (error) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          Error loading technical data: {error.message}
        </Alert>
        <Box display="flex" gap={2}>
          <Button variant="outlined" onClick={() => refetch()}>
            Retry
          </Button>
          <Button variant="text" onClick={() => window.location.reload()}>
            Refresh Page
          </Button>
        </Box>
      </Container>
    );
  }

  // Get sample data for overview cards
  const sampleData = technicalData?.data?.data?.[0] || {};
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Technical Analysis - All Indicators
      </Typography>
      
      {/* Info Alert about data display */}
      <Alert severity="info" sx={{ mb: 3 }}>
        {symbolFilter ? (
          `Showing historical data for ${symbolFilter.toUpperCase()} (${timeframe})`
        ) : (
          `Showing latest ${timeframe} technical data for all symbols. Search for a specific symbol to view its historical data.`
        )}
      </Alert>
      
      {/* Controls */}
      <Box display="flex" gap={2} mb={3} alignItems="center" flexWrap="wrap">
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel>Timeframe</InputLabel>
          <Select
            value={timeframe}
            onChange={(e) => handleTimeframeChange(e.target.value)}
          >
            <MenuItem value="daily">Daily</MenuItem>
            <MenuItem value="weekly">Weekly</MenuItem>
            <MenuItem value="monthly">Monthly</MenuItem>
          </Select>
        </FormControl>
        
        <TextField
          label="Search Symbol"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
          onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          size="small"
          sx={{ minWidth: 150 }}
          placeholder="e.g., AAPL"
        />
        
        <Button
          variant="outlined"
          onClick={handleSearch}
          startIcon={<Search />}
          disabled={isLoading}
        >
          {symbolFilter ? 'Search' : 'Filter'}
        </Button>

        {symbolFilter && (
          <Button
            variant="text"
            onClick={handleClearSearch}
            disabled={isLoading}
          >
            Show All Symbols
          </Button>
        )}

        {/* Pagination Controls */}
        {!symbolFilter && (
          <Box sx={{ ml: 'auto', display: 'flex', gap: 1, alignItems: 'center' }}>
            <Button
              size="small"
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1 || isLoading}
            >
              Previous
            </Button>
            <Typography variant="body2">
              Page {page}
            </Typography>            <Button
              size="small"
              onClick={() => setPage(page + 1)}
              disabled={isLoading || (technicalData?.data?.data?.length || 0) < 25}
            >
              Next
            </Button>
          </Box>
        )}
      </Box>

      {/* Technical Indicators Overview */}
      {sampleData.symbol && (
        <Accordion sx={{ mb: 3 }}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography variant="h6">
              Technical Indicators Overview - {sampleData.symbol}
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={2}>
              {/* Oscillators */}
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom color="primary">
                  Oscillators
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TechnicalIndicatorCard
                  title="RSI (14)"
                  value={sampleData.rsi}
                  description="Relative Strength Index - Momentum oscillator"
                  type="rsi"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TechnicalIndicatorCard
                  title="MFI"
                  value={sampleData.mfi}
                  description="Money Flow Index - Volume-weighted RSI"
                  type="rsi"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TechnicalIndicatorCard
                  title="ADX"
                  value={sampleData.adx}
                  description="Average Directional Index - Trend strength"
                  type="adx"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TechnicalIndicatorCard
                  title="ATR"
                  value={sampleData.atr}
                  description="Average True Range - Volatility measure"
                  type="default"
                />
              </Grid>

              {/* MACD Group */}
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom color="primary" sx={{ mt: 2 }}>
                  MACD Indicators
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={4}>
                <TechnicalIndicatorCard
                  title="MACD Line"
                  value={sampleData.macd}
                  description="Moving Average Convergence Divergence"
                  type="macd"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={4}>
                <TechnicalIndicatorCard
                  title="MACD Signal"
                  value={sampleData.macd_signal}
                  description="MACD Signal Line"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={4}>
                <TechnicalIndicatorCard
                  title="MACD Histogram"
                  value={sampleData.macd_hist}
                  description="MACD - MACD Signal"
                  type="macd"
                />
              </Grid>

              {/* Moving Averages */}
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom color="primary" sx={{ mt: 2 }}>
                  Moving Averages
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TechnicalIndicatorCard
                  title="SMA 10"
                  value={sampleData.sma_10}
                  description="Simple Moving Average"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TechnicalIndicatorCard
                  title="SMA 20"
                  value={sampleData.sma_20}
                  description="Simple Moving Average"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TechnicalIndicatorCard
                  title="SMA 50"
                  value={sampleData.sma_50}
                  description="Simple Moving Average"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TechnicalIndicatorCard
                  title="SMA 150"
                  value={sampleData.sma_150}
                  description="Simple Moving Average"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TechnicalIndicatorCard
                  title="SMA 200"
                  value={sampleData.sma_200}
                  description="Simple Moving Average"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TechnicalIndicatorCard
                  title="EMA 21"
                  value={sampleData.ema_21}
                  description="Exponential Moving Average"
                  type="default"
                />
              </Grid>

              {/* Bollinger Bands */}
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom color="primary" sx={{ mt: 2 }}>
                  Bollinger Bands
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={4}>
                <TechnicalIndicatorCard
                  title="BB Upper"
                  value={sampleData.bbands_upper}
                  description="Bollinger Band Upper"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={4}>
                <TechnicalIndicatorCard
                  title="BB Middle"
                  value={sampleData.bbands_middle}
                  description="Bollinger Band Middle (SMA 20)"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={4}>
                <TechnicalIndicatorCard
                  title="BB Lower"
                  value={sampleData.bbands_lower}
                  description="Bollinger Band Lower"
                  type="default"
                />
              </Grid>

              {/* Momentum & Volume */}
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom color="primary" sx={{ mt: 2 }}>
                  Momentum & Volume Indicators
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TechnicalIndicatorCard
                  title="Momentum"
                  value={sampleData.mom}
                  description="Price momentum indicator"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TechnicalIndicatorCard
                  title="ROC"
                  value={sampleData.roc}
                  description="Rate of Change"
                  type="default"
                  unit="%"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TechnicalIndicatorCard
                  title="A/D Line"
                  value={sampleData.ad}
                  description="Accumulation/Distribution Line"
                  type="default"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <TechnicalIndicatorCard
                  title="CMF"
                  value={sampleData.cmf}
                  description="Chaikin Money Flow"
                  type="default"
                />
              </Grid>
            </Grid>
          </AccordionDetails>
        </Accordion>
      )}      {/* Comprehensive Data Table */}
      <Box mb={3}>
        <Typography variant="h6" gutterBottom>
          {symbolFilter ? (
            `${symbolFilter.toUpperCase()} Technical Data (${timeframe.charAt(0).toUpperCase() + timeframe.slice(1)})`
          ) : (
            `Latest Technical Data for All Symbols (${timeframe.charAt(0).toUpperCase() + timeframe.slice(1)})`
          )}
        </Typography>
        
        {technicalData?.data?.data?.length === 0 && !isLoading && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            No technical data found. {symbolFilter ? `Try a different symbol or timeframe.` : `No data available for this timeframe.`}
          </Alert>
        )}
          {isLoading ? (
          <Box display="flex" flexDirection="column" alignItems="center" p={4}>
            <CircularProgress sx={{ mb: 2 }} />
            <Typography variant="body2" color="text.secondary">
              {symbolFilter ? 
                `Loading historical data for ${symbolFilter.toUpperCase()}...` : 
                `Loading latest technical data for all symbols...`
              }
            </Typography>
          </Box>
        ) : (
          <ComprehensiveTechnicalTable />
        )}

        {/* Pagination for historical data */}
        {symbolFilter && technicalData?.data?.data?.length > 0 && (
          <Box display="flex" justifyContent="center" mt={2}>
            <Button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1 || isLoading}
              sx={{ mr: 2 }}
            >
              Previous
            </Button>
            <Typography variant="body2" sx={{ alignSelf: 'center', mx: 2 }}>
              Page {page}
            </Typography>            <Button
              onClick={() => setPage(page + 1)}
              disabled={isLoading || (technicalData?.data?.data?.length || 0) < 25}
            >
              Next
            </Button>
          </Box>
        )}
      </Box>
    </Container>
  );
}

export default TechnicalAnalysis;
