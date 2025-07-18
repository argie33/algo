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
    // Note: Download functionality would need to be implemented with a different approach for recharts
    console.log('Download functionality would be implemented here');
  };

  const chartData = processChartData();

  if (error) {
    return (
      <div className="bg-white shadow-md rounded-lg" sx={{ height: height }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">
            {String(error)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ height: isFullscreen ? '100vh' : height }}>
      <div className="bg-white shadow-md rounded-lg"Content sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        {/* Controls */}
        {showControls && (
          <div  sx={{ mb: 2 }}>
            <div className="grid" container spacing={2} alignItems="center">
              {/* Timeframe Buttons */}
              <div className="grid" item>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"Group size="small" variant="outlined">
                  {timeframes.map((tf) => (
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      key={tf.value}
                      variant={timeframe === tf.value ? 'contained' : 'outlined'}
                      onClick={() => handleTimeframeChange(tf.value)}
                    >
                      {tf.label}
                    </button>
                  ))}
                </ButtonGroup>
              </div>

              {/* Chart Type */}
              <div className="grid" item>
                <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Chart Type</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={chartType}
                    label="Chart Type"
                    onChange={handleChartTypeChange}
                  >
                    {chartTypes.map((type) => (
                      <option  key={type.value} value={type.value}>
                        <div  sx={{ display: 'flex', alignItems: 'center' }}>
                          {type.icon}
                          <div  sx={{ ml: 1 }}>{type.label}</div>
                        </div>
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Indicators */}
              <div className="grid" item>
                <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {availableIndicators.slice(0, 5).map((indicator) => (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                      key={indicator}
                      label={indicator}
                      size="small"
                      variant={indicators.includes(indicator) ? 'filled' : 'outlined'}
                      onClick={() => handleIndicatorToggle(indicator)}
                      color={indicators.includes(indicator) ? 'primary' : 'default'}
                    />
                  ))}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="grid" item sx={{ ml: 'auto' }}>
                <div  sx={{ display: 'flex', gap: 1 }}>
                  <div  title="Refresh">
                    <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={() => onRefresh(symbol, timeframe)}>
                      <Refresh />
                    </button>
                  </div>
                  <div  title="Download">
                    <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={handleDownload}>
                      <Download />
                    </button>
                  </div>
                  <div  title="Fullscreen">
                    <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={handleFullscreen}>
                      <Fullscreen />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Chart */}
        <div  sx={{ flexGrow: 1, position: 'relative' }}>
          {isLoading ? (
            <div  sx={{ 
              display: 'flex', 
              justifyContent: 'center', 
              alignItems: 'center', 
              height: '100%' 
            }}>
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
            </div>
          ) : chartData ? (
            <ResponsiveContainer width="100%" height="100%">
              {chartType === 'area' ? (
                <AreaChart data={chartData}>
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
                <LineChart data={chartData}>
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
            <div  sx={{ 
              display: 'flex', 
              justifyContent: 'center', 
              alignItems: 'center', 
              height: '100%' 
            }}>
              <div  color="text.secondary">
                No data available for {symbol}
              </div>
            </div>
          )}
        </div>

        {/* Real-time info */}
        {realTimeData && (
          <div  sx={{ mt: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div  variant="body2" color="text.secondary">
              Real-time data
            </div>
            <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <div  variant="h6">
                ${parseFloat(realTimeData.price).toFixed(2)}
              </div>
              {realTimeData.change && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  icon={realTimeData.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                  label={`${realTimeData.change >= 0 ? '+' : ''}${realTimeData.change.toFixed(2)} (${realTimeData.changePercent?.toFixed(2)}%)`}
                  color={realTimeData.change >= 0 ? 'success' : 'error'}
                  size="small"
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default StockChart;