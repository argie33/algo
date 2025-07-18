import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  ButtonGroup,
  Alert,
  CircularProgress,
  Chip
} from '@mui/material';
import {
  ShowChart,
  TrendingUp,
  TrendingDown,
  Timeline
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';
import { getStockPrices } from '../services/api';
import { format } from 'date-fns';

const HistoricalPriceChart = ({ symbol = 'AAPL', defaultPeriod = 30 }) => {
  const [period, setPeriod] = useState(defaultPeriod);
  const [timeframe, setTimeframe] = useState('daily');

  const { data: priceData, isLoading, error, refetch } = useQuery({
    queryKey: ['historical-prices', symbol, timeframe, period],
    queryFn: async () => {
      console.log(`Fetching ${timeframe} prices for ${symbol}, ${period} periods`);
      return await getStockPrices(symbol, timeframe, period);
    },
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 2
  });

  const formatPrice = (value) => {
    if (!value) return 'N/A';
    return `$${value.toFixed(2)}`;
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    try {
      return format(new Date(dateString), 'MMM dd, yyyy');
    } catch {
      return dateString;
    }
  };

  const formatTooltipDate = (dateString) => {
    if (!dateString) return '';
    try {
      return format(new Date(dateString), 'MMM dd, yyyy, h:mm a');
    } catch {
      return dateString;
    }
  };

  const chartData = priceData?.data || [];
  const latestPrice = chartData[0];
  const oldestPrice = chartData[chartData.length - 1];
  
  const priceChange = latestPrice && oldestPrice ? 
    latestPrice.close - oldestPrice.close : 0;
  const priceChangePct = latestPrice && oldestPrice && oldestPrice.close ? 
    (priceChange / oldestPrice.close) * 100 : 0;

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div 
          sx={{
            backgroundColor: 'background.paper',
            border: 1,
            borderColor: 'divider',
            borderRadius: 1,
            p: 2,
            boxShadow: 2
          }}
        >
          <div  variant="subtitle2" gutterBottom>
            {formatTooltipDate(label)}
          </div>
          <div  variant="body2">
            <strong>Open:</strong> {formatPrice(data.open)}
          </div>
          <div  variant="body2">
            <strong>High:</strong> {formatPrice(data.high)}
          </div>
          <div  variant="body2">
            <strong>Low:</strong> {formatPrice(data.low)}
          </div>
          <div  variant="body2">
            <strong>Close:</strong> {formatPrice(data.close)}
          </div>
          <div  variant="body2">
            <strong>Volume:</strong> {data.volume?.toLocaleString() || 'N/A'}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%' }}>
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <ShowChart sx={{ color: 'primary.main' }} />
            <div  variant="h6" sx={{ fontWeight: 600 }}>
              Historical Prices - {symbol}
            </div>
          </div>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            size="small"
            onClick={() => refetch()}
            disabled={isLoading}
            startIcon={<Timeline />}
          >
            Refresh
          </button>
        </div>

        {/* Controls */}
        <div  sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"Group size="small" variant="outlined">
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              onClick={() => setTimeframe('daily')}
              variant={timeframe === 'daily' ? 'contained' : 'outlined'}
            >
              Daily
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              onClick={() => setTimeframe('weekly')}
              variant={timeframe === 'weekly' ? 'contained' : 'outlined'}
            >
              Weekly
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              onClick={() => setTimeframe('monthly')}
              variant={timeframe === 'monthly' ? 'contained' : 'outlined'}
            >
              Monthly
            </button>
          </ButtonGroup>

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"Group size="small" variant="outlined">
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              onClick={() => setPeriod(30)}
              variant={period === 30 ? 'contained' : 'outlined'}
            >
              30 periods
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              onClick={() => setPeriod(90)}
              variant={period === 90 ? 'contained' : 'outlined'}
            >
              90 periods
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              onClick={() => setPeriod(252)}
              variant={period === 252 ? 'contained' : 'outlined'}
            >
              1 Year
            </button>
          </ButtonGroup>
        </div>

        {/* Price Summary */}
        {latestPrice && (
          <div  sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              label={`Current: ${formatPrice(latestPrice.close)}`}
              color="primary"
              variant="outlined"
            />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              icon={priceChange >= 0 ? <TrendingUp /> : <TrendingDown />}
              label={`${priceChange >= 0 ? '+' : ''}${formatPrice(priceChange)} (${priceChangePct.toFixed(2)}%)`}
              color={priceChange >= 0 ? 'success' : 'error'}
              variant="outlined"
            />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              label={`Volume: ${latestPrice.volume?.toLocaleString() || 'N/A'}`}
              variant="outlined"
            />
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div  sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
            <div  variant="subtitle2">Failed to load price data</div>
            <div  variant="body2">
              {error.message || 'Unknown error occurred'}
            </div>
          </div>
        )}

        {/* Chart */}
        {!isLoading && !error && chartData.length > 0 && (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData.reverse()}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="date" 
                tick={{ fontSize: 12 }}
                tickFormatter={formatDate}
              />
              <YAxis 
                tick={{ fontSize: 12 }}
                domain={['auto', 'auto']}
                tickFormatter={(value) => `$${value?.toFixed(2)}`}
              />
              <div  content={<CustomTooltip />} />
              <Line 
                type="monotone" 
                dataKey="close" 
                stroke="#1976d2" 
                strokeWidth={2} 
                dot={false}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}

        {/* No Data State */}
        {!isLoading && !error && chartData.length === 0 && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
            <div  variant="subtitle2">No price data available</div>
            <div  variant="body2">
              The price data for {symbol} ({timeframe}) is not yet loaded. 
              The price loaders need to populate the database tables.
            </div>
          </div>
        )}

        {/* Data Summary */}
        {chartData.length > 0 && (
          <div  sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: 'divider' }}>
            <div  variant="caption" color="text.secondary">
              Showing {chartData.length} {timeframe} data points for {symbol}
              {latestPrice && ` • Latest: ${formatDate(latestPrice.date)}`}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default HistoricalPriceChart;