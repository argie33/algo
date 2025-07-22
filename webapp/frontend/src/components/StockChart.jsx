import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  ButtonGroup,
  FormControl,
  Select,
  MenuItem,
  InputLabel,
  Grid,
  Chip,
  IconButton,
  Tooltip,
  CircularProgress,
  Alert
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  BarChart,
  Timeline,
  Fullscreen,
  Refresh,
  Settings,
  Download
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend as RechartsLegend
} from 'recharts';


const StockChart = ({ 
  symbol, 
  data, 
  isLoading = false, 
  error = null,
  onRefresh = () => {},
  height = 400,
  showControls = true,
  realTimeData = null
}) => {
  const [timeframe, setTimeframe] = useState('1D');
  const [chartType, setChartType] = useState('line');
  const [indicators, setIndicators] = useState([]);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const chartRef = useRef(null);

  const timeframes = [
    { value: '1D', label: '1D' },
    { value: '5D', label: '5D' },
    { value: '1M', label: '1M' },
    { value: '3M', label: '3M' },
    { value: '6M', label: '6M' },
    { value: '1Y', label: '1Y' },
    { value: '2Y', label: '2Y' },
    { value: '5Y', label: '5Y' },
    { value: 'MAX', label: 'MAX' }
  ];

  const chartTypes = [
    { value: 'line', label: 'Line', icon: <ShowChart /> },
    { value: 'candlestick', label: 'Candlestick', icon: <BarChart /> },
    { value: 'area', label: 'Area', icon: <Timeline /> }
  ];

  const availableIndicators = [
    'SMA20', 'SMA50', 'SMA200', 'EMA20', 'EMA50', 'Bollinger Bands', 'RSI', 'MACD', 'Volume'
  ];

  // Process data for Recharts
  const processChartData = () => {
    if (!data || !data.length) return null;

    return data.map((item, index) => {
      const prices = data.map(d => d.close || d.price);
      const point = {
        date: item.date || item.timestamp,
        price: item.close || item.price,
        volume: item.volume || 0,
        open: item.open || item.price,
        high: item.high || item.price,
        low: item.low || item.price,
        close: item.close || item.price
      };

      // Add technical indicators
      if (indicators.includes('SMA20')) {
        point.sma20 = calculateSMAAtIndex(prices, 20, index);
      }
      if (indicators.includes('SMA50')) {
        point.sma50 = calculateSMAAtIndex(prices, 50, index);
      }
      if (indicators.includes('SMA200')) {
        point.sma200 = calculateSMAAtIndex(prices, 200, index);
      }

      return point;
    });
  };

  // Calculate Simple Moving Average at specific index
  const calculateSMAAtIndex = (prices, period, index) => {
    if (index < period - 1) return null;
    const sum = prices.slice(index - period + 1, index + 1).reduce((a, b) => a + b, 0);
    return sum / period;
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value);
  };

  const formatVolume = (value) => {
    return new Intl.NumberFormat('en-US', {
      notation: 'compact',
      compactDisplay: 'short',
    }).format(value);
  };

  const handleTimeframeChange = (newTimeframe) => {
    setTimeframe(newTimeframe);
    onRefresh(symbol, newTimeframe);
  };

  const handleChartTypeChange = (event) => {
    setChartType(event.target.value);
  };

  const handleIndicatorToggle = (indicator) => {
    setIndicators(prev => 
      prev.includes(indicator) 
        ? prev.filter(i => i !== indicator)
        : [...prev, indicator]
    );
  };

  const handleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  const handleDownload = () => {
    // TODO: Implement download functionality for recharts
    // Could export as PNG/SVG using html2canvas or similar library
  };

  const chartData = processChartData();

  if (error) {
    return (
      <Card sx={{ height: height }}>
        <CardContent>
          <Alert severity="error">
            {String(error)}
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card sx={{ height: isFullscreen ? '100vh' : height }}>
      <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* Controls */}
        {showControls && (
          <Box sx={{ mb: 2 }}>
            <Grid container spacing={2} alignItems="center">
              {/* Timeframe Buttons */}
              <Grid item>
                <ButtonGroup size="small" variant="outlined">
                  {timeframes.map((tf) => (
                    <Button
                      key={tf.value}
                      variant={timeframe === tf.value ? 'contained' : 'outlined'}
                      onClick={() => handleTimeframeChange(tf.value)}
                    >
                      {tf.label}
                    </Button>
                  ))}
                </ButtonGroup>
              </Grid>

              {/* Chart Type */}
              <Grid item>
                <FormControl size="small" sx={{ minWidth: 120 }}>
                  <InputLabel>Chart Type</InputLabel>
                  <Select
                    value={chartType}
                    label="Chart Type"
                    onChange={handleChartTypeChange}
                  >
                    {chartTypes.map((type) => (
                      <MenuItem key={type.value} value={type.value}>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          {type.icon}
                          <Typography sx={{ ml: 1 }}>{type.label}</Typography>
                        </Box>
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>

              {/* Indicators */}
              <Grid item>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {availableIndicators.slice(0, 5).map((indicator) => (
                    <Chip
                      key={indicator}
                      label={indicator}
                      size="small"
                      variant={indicators.includes(indicator) ? 'filled' : 'outlined'}
                      onClick={() => handleIndicatorToggle(indicator)}
                      color={indicators.includes(indicator) ? 'primary' : 'default'}
                    />
                  ))}
                </Box>
              </Grid>

              {/* Action Buttons */}
              <Grid item sx={{ ml: 'auto' }}>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Tooltip title="Refresh">
                    <IconButton size="small" onClick={() => onRefresh(symbol, timeframe)}>
                      <Refresh />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Download">
                    <IconButton size="small" onClick={handleDownload}>
                      <Download />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Fullscreen">
                    <IconButton size="small" onClick={handleFullscreen}>
                      <Fullscreen />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Grid>
            </Grid>
          </Box>
        )}

        {/* Chart */}
        <Box sx={{ flexGrow: 1, position: 'relative' }}>
          {isLoading ? (
            <Box sx={{ 
              display: 'flex', 
              justifyContent: 'center', 
              alignItems: 'center', 
              height: '100%' 
            }}>
              <CircularProgress />
            </Box>
          ) : chartData ? (
            <ResponsiveContainer width="100%" height="100%">
              {chartType === 'area' ? (
                <AreaChart data={chartData} aria-label="area">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="date" 
                    type="category"
                    scale="time"
                    tickFormatter={(value) => new Date(value).toLocaleDateString()}
                  />
                  <YAxis 
                    tickFormatter={formatCurrency}
                    domain={['dataMin - 0.01', 'dataMax + 0.01']}
                  />
                  <RechartsTooltip 
                    formatter={(value, name) => [formatCurrency(value), name]}
                    labelFormatter={(value) => new Date(value).toLocaleString()}
                  />
                  <RechartsLegend />
                  <Area 
                    type="monotone" 
                    dataKey="price" 
                    stroke="rgb(75, 192, 192)" 
                    fill="rgba(75, 192, 192, 0.2)"
                    name={`${symbol} Price`}
                  />
                  {indicators.includes('SMA20') && (
                    <Line type="monotone" dataKey="sma20" stroke="rgb(255, 206, 86)" name="SMA 20" strokeWidth={2} dot={false} />
                  )}
                  {indicators.includes('SMA50') && (
                    <Line type="monotone" dataKey="sma50" stroke="rgb(255, 99, 132)" name="SMA 50" strokeWidth={2} dot={false} />
                  )}
                  {indicators.includes('SMA200') && (
                    <Line type="monotone" dataKey="sma200" stroke="rgb(54, 162, 235)" name="SMA 200" strokeWidth={2} dot={false} />
                  )}
                </AreaChart>
              ) : (
                <LineChart data={chartData} aria-label="line">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="date" 
                    type="category"
                    scale="time"
                    tickFormatter={(value) => new Date(value).toLocaleDateString()}
                  />
                  <YAxis 
                    tickFormatter={formatCurrency}
                    domain={['dataMin - 0.01', 'dataMax + 0.01']}
                  />
                  <RechartsTooltip 
                    formatter={(value, name) => [formatCurrency(value), name]}
                    labelFormatter={(value) => new Date(value).toLocaleString()}
                  />
                  <RechartsLegend />
                  <Line 
                    type="monotone" 
                    dataKey="price" 
                    stroke="rgb(75, 192, 192)" 
                    strokeWidth={2}
                    dot={false}
                    name={`${symbol} Price`}
                  />
                  {indicators.includes('SMA20') && (
                    <Line type="monotone" dataKey="sma20" stroke="rgb(255, 206, 86)" name="SMA 20" strokeWidth={2} dot={false} />
                  )}
                  {indicators.includes('SMA50') && (
                    <Line type="monotone" dataKey="sma50" stroke="rgb(255, 99, 132)" name="SMA 50" strokeWidth={2} dot={false} />
                  )}
                  {indicators.includes('SMA200') && (
                    <Line type="monotone" dataKey="sma200" stroke="rgb(54, 162, 235)" name="SMA 200" strokeWidth={2} dot={false} />
                  )}
                </LineChart>
              )}
            </ResponsiveContainer>
          ) : (
            <Box sx={{ 
              display: 'flex', 
              justifyContent: 'center', 
              alignItems: 'center', 
              height: '100%' 
            }}>
              <Typography color="text.secondary">
                No data available for {symbol}
              </Typography>
            </Box>
          )}
        </Box>

        {/* Real-time info */}
        {realTimeData && (
          <Box sx={{ mt: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2" color="text.secondary">
              Real-time data
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="h6">
                ${parseFloat(realTimeData.price).toFixed(2)}
              </Typography>
              {realTimeData.change && (
                <Chip
                  icon={realTimeData.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                  label={`${realTimeData.change >= 0 ? '+' : ''}${realTimeData.change.toFixed(2)} (${realTimeData.changePercent?.toFixed(2)}%)`}
                  color={realTimeData.change >= 0 ? 'success' : 'error'}
                  size="small"
                />
              )}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default StockChart;