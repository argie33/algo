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
import { MoreVert, TrendingUp, TrendingDown } from '@mui/icons-material';
import StockChart from './StockChart';
import simpleAlpacaWebSocket from '../services/simpleAlpacaWebSocket';
import { useSimpleFetch } from '../hooks/useSimpleFetch.js';
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
  const { data: chartData, isLoading, error, refetch } = useSimpleFetch({
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
        console.error('Historical data API failed:', error);
        throw new Error('Chart data unavailable - please check your API connection');
      }
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

  // Mock data generation removed - now using only real market data

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent sx={{ height: '100%', p: 2 }}>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h6" fontWeight="bold">
              {symbol} Chart
            </Typography>
            {isConnected && (
              <Chip 
                label="LIVE" 
                color="success" 
                size="small" 
                sx={{ animation: 'pulse 2s infinite' }}
              />
            )}
            {realTimePrice && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="h6">
                  ${realTimePrice.price.toFixed(2)}
                </Typography>
                <Chip
                  icon={realTimePrice.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                  label={`${realTimePrice.change >= 0 ? '+' : ''}${realTimePrice.change.toFixed(2)} (${realTimePrice.changePercent.toFixed(2)}%)`}
                  color={realTimePrice.change >= 0 ? 'success' : 'error'}
                  size="small"
                />
              </Box>
            )}
          </Box>
          
          <IconButton onClick={handleMenuOpen}>
            <MoreVert />
          </IconButton>
          
          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={handleMenuClose}
          >
            <MenuItem disabled>
              <Typography variant="caption">Timeframe</Typography>
            </MenuItem>
            {['1D', '5D', '1M', '3M', '6M', '1Y', '2Y', '5Y', 'MAX'].map(tf => (
              <MenuItem 
                key={tf} 
                onClick={() => handleTimeframeChange(tf)}
                selected={selectedTimeframe === tf}
              >
                {tf}
              </MenuItem>
            ))}
          </Menu>
        </Box>

        {/* Chart */}
        {error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load chart data. Please check your API connection.
          </Alert>
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
      </CardContent>
    </Card>
  );
};

export default DashboardStockChart;