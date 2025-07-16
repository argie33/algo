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
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip as ChartTooltip,
  Legend,
  Filler,
  TimeScale
} from 'chart.js';
import { Line, Bar, Chart } from 'react-chartjs-2';
import 'chartjs-adapter-date-fns';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  ChartTooltip,
  Legend,
  Filler,
  TimeScale
);

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

  // Process data for Chart.js
  const processChartData = () => {
    if (!data || !data.length) return null;

    const labels = data.map(item => new Date(item.date || item.timestamp));
    const prices = data.map(item => item.close || item.price);
    const volumes = data.map(item => item.volume || 0);

    // Base dataset
    const datasets = [];

    if (chartType === 'line') {
      datasets.push({
        label: `${symbol} Price`,
        data: prices,
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.1)',
        borderWidth: 2,
        fill: false,
        tension: 0.1,
        pointRadius: 0,
        pointHoverRadius: 5,
      });
    } else if (chartType === 'area') {
      datasets.push({
        label: `${symbol} Price`,
        data: prices,
        borderColor: 'rgb(75, 192, 192)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        borderWidth: 2,
        fill: true,
        tension: 0.1,
        pointRadius: 0,
        pointHoverRadius: 5,
      });
    } else if (chartType === 'candlestick') {
      // For candlestick, we need OHLC data
      const candlestickData = data.map(item => ({
        x: new Date(item.date || item.timestamp),
        o: item.open || item.price,
        h: item.high || item.price,
        l: item.low || item.price,
        c: item.close || item.price
      }));

      datasets.push({
        label: `${symbol} OHLC`,
        data: candlestickData,
        borderColor: 'rgb(255, 99, 132)',
        backgroundColor: 'rgba(255, 99, 132, 0.1)',
      });
    }

    // Add volume dataset if available
    if (volumes.some(v => v > 0) && indicators.includes('Volume')) {
      datasets.push({
        label: 'Volume',
        data: volumes,
        type: 'bar',
        backgroundColor: 'rgba(153, 102, 255, 0.3)',
        borderColor: 'rgba(153, 102, 255, 1)',
        borderWidth: 1,
        yAxisID: 'y1',
      });
    }

    // Add technical indicators
    if (indicators.includes('SMA20')) {
      const sma20 = calculateSMA(prices, 20);
      datasets.push({
        label: 'SMA 20',
        data: sma20,
        borderColor: 'rgb(255, 206, 86)',
        backgroundColor: 'rgba(255, 206, 86, 0.1)',
        borderWidth: 1,
        fill: false,
        pointRadius: 0,
      });
    }

    if (indicators.includes('SMA50')) {
      const sma50 = calculateSMA(prices, 50);
      datasets.push({
        label: 'SMA 50',
        data: sma50,
        borderColor: 'rgb(255, 99, 132)',
        backgroundColor: 'rgba(255, 99, 132, 0.1)',
        borderWidth: 1,
        fill: false,
        pointRadius: 0,
      });
    }

    if (indicators.includes('SMA200')) {
      const sma200 = calculateSMA(prices, 200);
      datasets.push({
        label: 'SMA 200',
        data: sma200,
        borderColor: 'rgb(54, 162, 235)',
        backgroundColor: 'rgba(54, 162, 235, 0.1)',
        borderWidth: 1,
        fill: false,
        pointRadius: 0,
      });
    }

    // Add real-time data point if available
    if (realTimeData && realTimeData.price) {
      const currentPrice = parseFloat(realTimeData.price);
      const lastPrice = prices[prices.length - 1];
      const priceChange = currentPrice - lastPrice;
      
      datasets.push({
        label: 'Real-time Price',
        data: [{ x: new Date(), y: currentPrice }],
        borderColor: priceChange >= 0 ? 'rgb(76, 175, 80)' : 'rgb(244, 67, 54)',
        backgroundColor: priceChange >= 0 ? 'rgba(76, 175, 80, 0.8)' : 'rgba(244, 67, 54, 0.8)',
        pointRadius: 6,
        pointHoverRadius: 8,
        showLine: false,
      });
    }

    return { labels, datasets };
  };

  // Calculate Simple Moving Average
  const calculateSMA = (prices, period) => {
    const sma = [];
    for (let i = 0; i < prices.length; i++) {
      if (i < period - 1) {
        sma.push(null);
      } else {
        const sum = prices.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
        sma.push(sum / period);
      }
    }
    return sma;
  };

  // Chart options
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    plugins: {
      legend: {
        position: 'top',
        labels: {
          usePointStyle: true,
          pointStyle: 'circle',
        },
      },
      title: {
        display: true,
        text: `${symbol} - ${timeframe}`,
        font: {
          size: 16,
          weight: 'bold',
        },
      },
      tooltip: {
        callbacks: {
          label: function(context) {
            let label = context.dataset.label || '';
            if (label) {
              label += ': ';
            }
            if (context.parsed.y !== null) {
              label += new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
              }).format(context.parsed.y);
            }
            return label;
          },
        },
      },
    },
    scales: {
      x: {
        type: 'time',
        time: {
          displayFormats: {
            hour: 'HH:mm',
            day: 'MMM dd',
            week: 'MMM dd',
            month: 'MMM yyyy',
            quarter: 'MMM yyyy',
            year: 'yyyy',
          },
        },
        title: {
          display: true,
          text: 'Date',
        },
      },
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        title: {
          display: true,
          text: 'Price ($)',
        },
        ticks: {
          callback: function(value) {
            return new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
            }).format(value);
          },
        },
      },
      y1: {
        type: 'linear',
        display: indicators.includes('Volume'),
        position: 'right',
        title: {
          display: true,
          text: 'Volume',
        },
        grid: {
          drawOnChartArea: false,
        },
        ticks: {
          callback: function(value) {
            return new Intl.NumberFormat('en-US', {
              notation: 'compact',
              compactDisplay: 'short',
            }).format(value);
          },
        },
      },
    },
    elements: {
      point: {
        radius: 0,
        hoverRadius: 5,
      },
      line: {
        tension: 0.1,
      },
    },
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
    if (chartRef.current) {
      const canvas = chartRef.current.canvas;
      const url = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.download = `${symbol}_chart_${timeframe}.png`;
      link.href = url;
      link.click();
    }
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
            <Line
              ref={chartRef}
              data={chartData}
              options={chartOptions}
              height={null}
            />
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