import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Typography,
  Grid,
  Paper,
  CircularProgress,
  Alert
} from '@mui/material';
import { api } from '../services/api';

const StockDetailSimple = () => {
  const { ticker } = useParams();
  const [stockData, setStockData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchStockData = async () => {
      try {
        setLoading(true);
        const response = await api.get(`/market/data/${ticker}`);
        if (response.success) {
          setStockData(response.data);
        } else {
          setError('Failed to load stock data');
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (ticker) {
      fetchStockData();
    }
  }, [ticker]);

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" mt={4}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ mt: 2 }}>
        {error}
      </Alert>
    );
  }

  return (
    <Box sx={{ p: 2 }}>
      <Paper sx={{ p: 3 }}>
        <Typography variant="h5" gutterBottom>
          {stockData?.symbol || ticker} - {stockData?.companyName || 'Company Name'}
        </Typography>
        
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <Typography variant="h6">
              Price: ${stockData?.price?.toFixed(2) || '0.00'}
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography 
              variant="h6" 
              color={stockData?.changePercent >= 0 ? 'success.main' : 'error.main'}
            >
              Change: {stockData?.changePercent >= 0 ? '+' : ''}{stockData?.changePercent?.toFixed(2) || '0.00'}%
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="body1">
              Volume: {stockData?.volume ? stockData.volume.toLocaleString() : 'N/A'}
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Typography variant="body1">
              Market Cap: ${stockData?.marketCap ? (stockData.marketCap / 1e9).toFixed(2) + 'B' : 'N/A'}
            </Typography>
          </Grid>
        </Grid>
      </Paper>
    </Box>
  );
};

export default StockDetailSimple;