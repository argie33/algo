import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  CircularProgress,
  Alert,
  IconButton,
  Menu,
  MenuItem,
  Chip
} from '@mui/material';
import StockChart from './StockChart';
import simpleAlpacaWebSocket from '../services/simpleAlpacaWebSocket';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const DashboardStockChart = ({ 
  symbol = 'SPY', 
  height = 400,
  showRealTime = true,
  autoRefresh = true
}) => {
  const [realTimePrice, setRealTimePrice] = useState(null);
  const [anchorEl, setAnchorEl] = useState(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState('1D');
  const [isConnected, setIsConnected] = useState(false);

  // Fetch historical data
  const { data: chartData, isLoading, error, refetch } = useQuery({
    queryKey: ['stock-chart', symbol, selectedTimeframe],
    queryFn: async () => {
      // Map timeframe to API period
      const periodMap = {
        '1D': 1,
        '5D': 5,
        '1M': 30,
        '3M': 90,
        '6M': 180,
        '1Y': 365,
        '2Y': 730,
        '5Y': 1825,
        'MAX': 3650
      };
      
      const period = periodMap[selectedTimeframe] || 30;
      
      try {
        // Try real API first
        const response = await axios.get(`/api/stocks/${symbol}/historical`, {
          params: { period }
        });
        
        if (response.data.success && response.data.data) {
          return response.data.data.map(item => ({
            date: item.date,
            timestamp: new Date(item.date).getTime(),
            open: item.open,
            high: item.high,
            low: item.low,
            close: item.close,
            volume: item.volume
          }));
        }
      } catch (error) {
        console.warn('Using mock data for chart:', error);
      }
      
      // Mock data fallback
      return generateMockChartData(period);
    },
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: autoRefresh ? 60 * 1000 : false
  });

  // Real-time data subscription
  useEffect(() => {
    if (!showRealTime) return;

    const handleConnected = () => {
      setIsConnected(true);
      simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
      simpleAlpacaWebSocket.subscribeToTrades([symbol]);
    };

    const handleDisconnected = () => {
      setIsConnected(false);
    };

    const handleData = ({ type, data }) => {
      if (data.symbol === symbol) {
        const price = data.price || data.ask || data.bid;
        if (price) {
          const lastClose = chartData?.[chartData.length - 1]?.close || price;
          const change = price - lastClose;
          const changePercent = (change / lastClose) * 100;
          
          setRealTimePrice({
            price,
            change,
            changePercent,
            timestamp: new Date().toISOString()
          });
        }
      }
    };

    simpleAlpacaWebSocket.on('connected', handleConnected);
    simpleAlpacaWebSocket.on('disconnected', handleDisconnected);
    simpleAlpacaWebSocket.on('data', handleData);

    // Connect if not already connected (silently handle auth failures)
    if (!simpleAlpacaWebSocket.isConnected) {
      simpleAlpacaWebSocket.connect().catch(error => {
        console.warn('Alpaca WebSocket connection not available:', error.message);
        // Don't spam the console with errors for normal auth failures
      });
    }

    return () => {
      simpleAlpacaWebSocket.off('connected', handleConnected);
      simpleAlpacaWebSocket.off('disconnected', handleDisconnected);
      simpleAlpacaWebSocket.off('data', handleData);
    };
  }, [symbol, showRealTime, chartData]);

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleTimeframeChange = (timeframe) => {
    setSelectedTimeframe(timeframe);
    handleMenuClose();
  };

  const handleRefresh = () => {
    refetch();
  };

  // Generate mock chart data
  function generateMockChartData(days) {
    const data = [];
    const now = new Date();
    let price = 450; // Starting price for SPY
    
    for (let i = days; i >= 0; i--) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      
      // Generate realistic OHLCV data
      const change = (Math.random() - 0.5) * 4;
      price = Math.max(price + change, 1);
      
      const dayVolatility = Math.random() * 2 + 0.5;
      const open = price + (Math.random() - 0.5) * dayVolatility;
      const close = price + (Math.random() - 0.5) * dayVolatility;
      const high = Math.max(open, close) + Math.random() * dayVolatility;
      const low = Math.min(open, close) - Math.random() * dayVolatility;
      
      data.push({
        date: date.toISOString().split('T')[0],
        timestamp: date.getTime(),
        open: parseFloat(open.toFixed(2)),
        high: parseFloat(high.toFixed(2)),
        low: parseFloat(low.toFixed(2)),
        close: parseFloat(close.toFixed(2)),
        volume: Math.floor(50000000 + Math.random() * 100000000)
      });
    }
    
    return data;
  }

  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%' }}>
      <div className="bg-white shadow-md rounded-lg"Content sx={{ height: '100%', p: 2 }}>
        {/* Header */}
        <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <div  variant="h6" fontWeight="bold">
              {symbol} Chart
            </div>
            {isConnected && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label="LIVE" 
                color="success" 
                size="small" 
                sx={{ animation: 'pulse 2s infinite' }}
              />
            )}
            {realTimePrice && (
              <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <div  variant="h6">
                  ${realTimePrice.price.toFixed(2)}
                </div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  icon={realTimePrice.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                  label={`${realTimePrice.change >= 0 ? '+' : ''}${realTimePrice.change.toFixed(2)} (${realTimePrice.changePercent.toFixed(2)}%)`}
                  color={realTimePrice.change >= 0 ? 'success' : 'error'}
                  size="small"
                />
              </div>
            )}
          </div>
          
          <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleMenuOpen}>
            <MoreVert />
          </button>
          
          <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg z-10"
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={handleMenuClose}
          >
            <option  disabled>
              <div  variant="caption">Timeframe</div>
            </option>
            {['1D', '5D', '1M', '3M', '6M', '1Y', '2Y', '5Y', 'MAX'].map(tf => (
              <option  
                key={tf} 
                onClick={() => handleTimeframeChange(tf)}
                selected={selectedTimeframe === tf}
              >
                {tf}
              </option>
            ))}
          </div>
        </div>

        {/* Chart */}
        {error ? (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
            Failed to load chart data. Using sample data.
          </div>
        ) : (
          <StockChart
            symbol={symbol}
            data={chartData}
            isLoading={isLoading}
            error={null}
            onRefresh={handleRefresh}
            height={height - 120}
            showControls={false}
            realTimeData={realTimePrice}
          />
        )}
      </div>
    </div>
  );
};

export default DashboardStockChart;