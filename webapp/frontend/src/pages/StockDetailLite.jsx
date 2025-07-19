import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  CircularProgress,
  Alert
} from '@mui/material';
import { TrendingUp, TrendingDown } from '@mui/icons-material';
import api from '../services/api';

const StockDetailLite = () => {
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

  const isPositive = stockData?.changePercent >= 0;

  return (
    <Box sx={{ p: 3 }}>
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center">
                <Box>
                  <Typography variant="h4" component="h1">
                    {stockData?.symbol || ticker}
                  </Typography>
                  <Typography variant="h6" color="text.secondary">
                    {stockData?.companyName || 'Company Name'}
                  </Typography>
                </Box>
                <Box textAlign="right">
                  <Typography variant="h5">
                    ${stockData?.price?.toFixed(2) || '0.00'}
                  </Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    {isPositive ? (
                      <TrendingUp color="success" />
                    ) : (
                      <TrendingDown color="error" />
                    )}
                    <Chip
                      label={`${isPositive ? '+' : ''}${stockData?.changePercent?.toFixed(2) || '0.00'}%`}
                      color={isPositive ? 'success' : 'error'}
                      size="small"
                    />
                  </Box>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Key Metrics
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Market Cap
                  </Typography>
                  <Typography variant="body1">
                    ${stockData?.marketCap ? (stockData.marketCap / 1e9).toFixed(2) + 'B' : 'N/A'}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Volume
                  </Typography>
                  <Typography variant="body1">
                    {stockData?.volume ? stockData.volume.toLocaleString() : 'N/A'}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    P/E Ratio
                  </Typography>
                  <Typography variant="body1">
                    {stockData?.peRatio?.toFixed(2) || 'N/A'}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    52W High
                  </Typography>
                  <Typography variant="body1">
                    ${stockData?.week52High?.toFixed(2) || 'N/A'}
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Trading Info
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Day Range
                  </Typography>
                  <Typography variant="body1">
                    ${stockData?.dayLow?.toFixed(2) || '0.00'} - ${stockData?.dayHigh?.toFixed(2) || '0.00'}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Avg Volume
                  </Typography>
                  <Typography variant="body1">
                    {stockData?.avgVolume ? stockData.avgVolume.toLocaleString() : 'N/A'}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Beta
                  </Typography>
                  <Typography variant="body1">
                    {stockData?.beta?.toFixed(2) || 'N/A'}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    52W Low
                  </Typography>
                  <Typography variant="body1">
                    ${stockData?.week52Low?.toFixed(2) || 'N/A'}
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default StockDetailLite;