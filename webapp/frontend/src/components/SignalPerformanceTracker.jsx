import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  LinearProgress,
  useTheme,
  alpha,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Avatar,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  Assessment,
  Speed,
  Timeline,
} from '@mui/icons-material';

const SignalPerformanceTracker = ({ symbols = [], timeframe = "7d" }) => {
  const theme = useTheme();
  const [performanceData, setPerformanceData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState({
    totalSignals: 0,
    profitableSignals: 0,
    avgReturn: 0,
    winRate: 0,
    bestPerformer: null,
    worstPerformer: null,
  });

  useEffect(() => {
    if (symbols.length > 0) {
      loadPerformanceData();
    }
  }, [symbols, timeframe]);

  const loadPerformanceData = async () => {
    try {
      setLoading(true);

      // Call real API for signal performance data
      if (symbols.length === 0) {
        setPerformanceData([]);
        setMetrics({
          totalSignals: 0,
          profitableSignals: 0,
          avgReturn: 0,
          winRate: 0,
          bestPerformer: null,
          worstPerformer: null,
        });
        return;
      }

      // Fetch performance data for each symbol
      const performancePromises = symbols.map(async (symbol) => {
        try {
          const response = await fetch(`http://localhost:3001/api/signals/performance/${symbol}?timeframe=${timeframe}`);
          if (response.ok) {
            return await response.json();
          }
        } catch (error) {
          console.warn(`Failed to fetch performance for ${symbol}:`, error);
        }
        return null;
      });

      const performanceResults = await Promise.all(performancePromises);
      const validPerformanceData = performanceResults.filter(data => data !== null);

      setPerformanceData(validPerformanceData);

      // Calculate metrics
      if (validPerformanceData.length > 0) {
        const totalSignals = validPerformanceData.length;
        const profitableSignals = validPerformanceData.filter(p => p.currentReturn > 0).length;
        const avgReturn = validPerformanceData.reduce((sum, p) => sum + p.currentReturn, 0) / totalSignals;
        const winRate = (profitableSignals / totalSignals) * 100;
        const bestPerformer = validPerformanceData.reduce((best, current) =>
          current.currentReturn > (best?.currentReturn || -Infinity) ? current : best, null);
        const worstPerformer = validPerformanceData.reduce((worst, current) =>
          current.currentReturn < (worst?.currentReturn || Infinity) ? current : worst, null);

        setMetrics({
          totalSignals,
          profitableSignals,
          avgReturn,
          winRate,
          bestPerformer,
          worstPerformer,
        });
      } else {
        setMetrics({
          totalSignals: 0,
          profitableSignals: 0,
          avgReturn: 0,
          winRate: 0,
          bestPerformer: null,
          worstPerformer: null,
        });
      }

    } catch (error) {
      console.error('Error loading performance data:', error);
      setPerformanceData([]);
    } finally {
      setLoading(false);
    }
  };

  const getSignalIcon = (signal) => {
    switch (signal?.toUpperCase()) {
      case 'BUY': return <TrendingUp sx={{ color: theme.palette.success.main }} />;
      case 'SELL': return <TrendingDown sx={{ color: theme.palette.error.main }} />;
      case 'HOLD': return <ShowChart sx={{ color: theme.palette.warning.main }} />;
      default: return <Assessment sx={{ color: theme.palette.grey[500] }} />;
    }
  };

  const getReturnColor = (returnValue) => {
    if (returnValue > 0) return theme.palette.success.main;
    if (returnValue < 0) return theme.palette.error.main;
    return theme.palette.grey[500];
  };

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Signal Performance Tracker
          </Typography>
          <LinearProgress />
        </CardContent>
      </Card>
    );
  }

  return (
    <Box>
      {/* Performance Metrics Overview */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={2}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Avatar sx={{ bgcolor: 'primary.main', mx: 'auto', mb: 1 }}>
                <Assessment />
              </Avatar>
              <Typography variant="h6" fontWeight="bold">
                {metrics.totalSignals}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Total Signals
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={2}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Avatar sx={{ bgcolor: 'success.main', mx: 'auto', mb: 1 }}>
                <TrendingUp />
              </Avatar>
              <Typography variant="h6" fontWeight="bold" color="success.main">
                {metrics.profitableSignals}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Profitable
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={2}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Avatar sx={{ bgcolor: 'info.main', mx: 'auto', mb: 1 }}>
                <Speed />
              </Avatar>
              <Typography
                variant="h6"
                fontWeight="bold"
                color={getReturnColor(metrics.avgReturn)}
              >
                {metrics.avgReturn != null
                  ? `${metrics.avgReturn > 0 ? '+' : ''}${metrics.avgReturn.toFixed(1)}%`
                  : 'N/A'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Avg Return
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={2}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Avatar sx={{ bgcolor: 'warning.main', mx: 'auto', mb: 1 }}>
                <Timeline />
              </Avatar>
              <Typography variant="h6" fontWeight="bold">
                {metrics.winRate != null ? `${metrics.winRate.toFixed(1)}%` : 'N/A'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Win Rate
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={2}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Avatar sx={{ bgcolor: 'success.main', mx: 'auto', mb: 1 }}>
                <TrendingUp />
              </Avatar>
              <Typography variant="h6" fontWeight="bold" color="success.main">
                {metrics.bestPerformer && metrics.bestPerformer.currentReturn != null
                  ? `+${metrics.bestPerformer.currentReturn.toFixed(1)}%`
                  : '--'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Best Signal
              </Typography>
              {metrics.bestPerformer && (
                <Typography variant="caption" display="block">
                  {metrics.bestPerformer.symbol}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={2}>
          <Card>
            <CardContent sx={{ textAlign: 'center' }}>
              <Avatar sx={{ bgcolor: 'error.main', mx: 'auto', mb: 1 }}>
                <TrendingDown />
              </Avatar>
              <Typography variant="h6" fontWeight="bold" color="error.main">
                {metrics.worstPerformer && metrics.worstPerformer.currentReturn != null
                  ? `${metrics.worstPerformer.currentReturn.toFixed(1)}%`
                  : '--'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Worst Signal
              </Typography>
              {metrics.worstPerformer && (
                <Typography variant="caption" display="block">
                  {metrics.worstPerformer.symbol}
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Detailed Performance Table */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Signal Performance Details
          </Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Signal</TableCell>
                  <TableCell align="right">Confidence</TableCell>
                  <TableCell align="right">Signal Date</TableCell>
                  <TableCell align="right">Days Held</TableCell>
                  <TableCell align="right">Current Return</TableCell>
                  <TableCell align="right">Performance</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {performanceData.map((performance, index) => (
                  <TableRow key={`${performance.symbol}-${index}`}>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {performance.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        {getSignalIcon(performance.signal)}
                        <Chip
                          label={performance.signal}
                          size="small"
                          color={
                            performance.signal === 'BUY' ? 'success' :
                            performance.signal === 'SELL' ? 'error' : 'warning'
                          }
                        />
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {performance.confidence != null
                          ? `${(performance.confidence * 100).toFixed(0)}%`
                          : 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {performance.signalDate}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {performance.daysHeld}d
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography
                        variant="body2"
                        fontWeight="bold"
                        color={getReturnColor(performance.currentReturn)}
                      >
                        {performance.currentReturn != null
                          ? `${performance.currentReturn > 0 ? '+' : ''}${performance.currentReturn.toFixed(1)}%`
                          : 'N/A'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <LinearProgress
                        variant="determinate"
                        value={performance.currentReturn != null ? Math.min(Math.abs(performance.currentReturn) * 5, 100) : 0}
                        sx={{
                          width: 60,
                          height: 6,
                          borderRadius: 3,
                          backgroundColor: alpha(theme.palette.grey[300], 0.3),
                          '& .MuiLinearProgress-bar': {
                            backgroundColor: getReturnColor(performance.currentReturn),
                          },
                        }}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Box>
  );
};

export default SignalPerformanceTracker;